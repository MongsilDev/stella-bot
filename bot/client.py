import asyncio
import logging
import time
from collections import deque

import discord
import sentry_sdk

from bot.detect import detect_direction
from bot.formatting import build_reply_line, jump_url, split_text
from bot.mapping import MapRow, MessageMap
from bot.masking import mask, strip_discord_tokens, unmask
from bot.translator import DeepLClient, QuotaExceeded, TranslationError

log = logging.getLogger("stella-bot")
WEBHOOK_NAME = "stella-bot"
NO_MENTIONS = discord.AllowedMentions.none()
QUOTA_REPORT_INTERVAL = 3600


class StellaBot(discord.Client):
    def __init__(
        self,
        *,
        channel_id: int,
        translator: DeepLClient,
        mapping: MessageMap,
        allow_bots: bool = False,
    ):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.translator = translator
        self.mapping = mapping
        self.allow_bots = allow_bots
        self._webhook: discord.Webhook | None = None
        self._recent: deque[str] = deque(maxlen=5)
        self._quota_reported_at: float | None = None

    async def on_ready(self):
        log.info("로그인: %s", self.user)
        await asyncio.gather(self._get_webhook(), self.translator.warmup())
        log.info("워밍업 완료")

    async def _get_webhook(self) -> discord.Webhook:
        if self._webhook is None:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(
                self.channel_id
            )
            for wh in await channel.webhooks():
                if wh.name == WEBHOOK_NAME and wh.user == self.user:
                    self._webhook = wh
                    break
            else:
                self._webhook = await channel.create_webhook(name=WEBHOOK_NAME)
        return self._webhook

    def _should_skip(self, message: discord.Message) -> bool:
        if message.channel.id != self.channel_id:
            return True
        reason = None
        if self._webhook and message.webhook_id == self._webhook.id:
            reason = "own webhook"
        elif message.author.bot and not self.allow_bots:
            reason = "bot author"
        elif not message.content.strip():
            reason = "empty content"
        if reason:
            log.debug("건너뜀 (메시지 %s): %s", message.id, reason)
            return True
        return False

    def _report_failure(self, e: Exception) -> None:
        if isinstance(e, QuotaExceeded):
            now = time.monotonic()
            last = self._quota_reported_at
            if last is not None and now - last < QUOTA_REPORT_INTERVAL:
                return
            self._quota_reported_at = now
        sentry_sdk.capture_exception(e)

    async def _send_parts(self, message: discord.Message, parts: list[str]) -> list[int]:
        """웹훅으로 조각을 순서대로 게시. 웹훅이 지워졌으면 다시 만들어 남은 조각을 한 번 더 보냄."""
        ids: list[int] = []
        retried = False
        while len(ids) < len(parts):
            webhook = await self._get_webhook()
            try:
                sent = await webhook.send(
                    parts[len(ids)],
                    username=message.author.display_name,
                    avatar_url=message.author.display_avatar.url,
                    wait=True,
                    allowed_mentions=NO_MENTIONS,
                )
            except discord.NotFound:
                if retried:
                    raise
                retried = True
                log.warning("웹훅이 없어 다시 가져옴 (메시지 %s)", message.id)
                self._webhook = None
                continue
            ids.append(sent.id)
        return ids

    async def _render(
        self, message: discord.Message, context: str | None
    ) -> tuple[str, str] | None:
        """게시할 본문과 방향 문자열을 반환. 번역 대상이 아니면 None."""
        direction = detect_direction(message.content)
        if direction is None:
            return None
        source, target = direction
        masked, spans = mask(message.content)
        translated, line = await asyncio.gather(
            self.translator.translate(masked, source, target, context=context),
            self._reply_line(message, target),
        )
        translated = unmask(translated, spans)
        if line:
            translated = f"{line}\n{translated}"
        return translated, f"{source}>{target}"

    async def _reply_line(self, message: discord.Message, target: str) -> str | None:
        ref = message.reference
        if ref is None or ref.message_id is None:
            return None
        row = await self.mapping.lookup(ref.message_id)
        if row is None:
            link_id = ref.message_id
        elif row.direction.endswith(target):
            link_id = row.trans_id
        else:
            link_id = row.orig_id
        url = jump_url(message.guild.id, self.channel_id, link_id)
        name = row.author_name if row else ""
        if not name:
            resolved = ref.resolved
            if isinstance(resolved, discord.Message):
                name = resolved.author.display_name
            else:
                try:
                    fetched = await message.channel.fetch_message(ref.message_id)
                    name = fetched.author.display_name
                except discord.HTTPException:
                    name = "원문"
        return build_reply_line(name, url)

    async def on_message(self, message: discord.Message):
        # 자기 웹훅 판별 전에 웹훅 캐시가 없으면 채워둔다
        if self._webhook is None and message.channel.id == self.channel_id:
            await self._get_webhook()
        if self._should_skip(message):
            return
        context = "\n".join(self._recent) or None
        self._recent.append(
            strip_discord_tokens(f"{message.author.display_name}: {message.content}")
        )
        try:
            started = time.monotonic()
            result = await self._render(message, context)
            if result is None:
                return
            translated, direction = result
            ids = await self._send_parts(message, split_text(translated))
            log.info("번역 게시 %dms", (time.monotonic() - started) * 1000)
            await self.mapping.add(
                MapRow(
                    orig_id=message.id,
                    trans_id=ids[0],
                    channel_id=self.channel_id,
                    author_id=message.author.id,
                    direction=direction,
                    author_name=message.author.display_name,
                    orig_text=message.content,
                    trans_text=translated,
                )
            )
        except (QuotaExceeded, TranslationError, discord.HTTPException) as e:
            log.warning("번역 실패 (메시지 %s): %s: %s", message.id, type(e).__name__, e)
            self._report_failure(e)
            try:
                await message.add_reaction("⚠️")
            except discord.HTTPException:
                pass

    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent):
        if payload.channel_id != self.channel_id:
            return
        row = await self.mapping.lookup(payload.message_id)
        if row is None or row.orig_id != payload.message_id:
            return
        try:
            channel = self.get_channel(self.channel_id) or await self.fetch_channel(
                self.channel_id
            )
            message = await channel.fetch_message(payload.message_id)
            result = await self._render(message, "\n".join(self._recent) or None)
            if result is None:
                return
            translated, _ = result
            webhook = await self._get_webhook()
            await webhook.edit_message(
                row.trans_id,
                content=split_text(translated)[0],
                allowed_mentions=NO_MENTIONS,
            )
            row.orig_text = message.content
            row.trans_text = translated
            await self.mapping.add(row)
        except discord.NotFound:
            pass
        except (QuotaExceeded, TranslationError) as e:
            log.warning("번역 실패 (수정 %s): %s: %s", payload.message_id, type(e).__name__, e)
            self._report_failure(e)

    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        if payload.channel_id != self.channel_id:
            return
        row = await self.mapping.lookup(payload.message_id)
        if row is None:
            return
        if row.orig_id == payload.message_id:
            try:
                webhook = await self._get_webhook()
                await webhook.delete_message(row.trans_id)
            except discord.NotFound:
                pass
        await self.mapping.delete(row.orig_id)
