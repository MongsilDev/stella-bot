from types import SimpleNamespace

import discord
import pytest

from bot import client as client_mod
from bot.client import StellaBot
from bot.mapping import MapRow, MessageMap
from bot.translator import QuotaExceeded


def _http_error(cls, status):
    resp = SimpleNamespace(status=status, reason="x")
    return cls(resp, "x")


class _Webhook:
    def __init__(self, wid=1, fail_send=0):
        self.id = wid
        self.fail_send = fail_send
        self.sent, self.edited, self.deleted = [], [], []
        self._next = 1000

    async def send(self, content, **kw):
        if self.fail_send:
            self.fail_send -= 1
            raise _http_error(discord.NotFound, 404)
        self._next += 1
        self.sent.append(content)
        return SimpleNamespace(id=self._next)

    async def edit_message(self, mid, content=None, **kw):
        self.edited.append((mid, content))

    async def delete_message(self, mid):
        self.deleted.append(mid)


class _Translator:
    def __init__(self, exc=None):
        self.exc = exc

    async def translate(self, text, source, target, context=None):
        if self.exc:
            raise self.exc
        return f"T:{text}"


class _Message:
    def __init__(self, mid, content):
        self.id = mid
        self.content = content
        self.author = SimpleNamespace(
            display_name="몽실", bot=False, id=42,
            display_avatar=SimpleNamespace(url="http://a"))
        self.channel = SimpleNamespace(id=7)
        self.webhook_id = None
        self.reference = None
        self.reactions = []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)


@pytest.fixture
async def bot():
    m = MessageMap()
    await m.open(":memory:")
    b = StellaBot(channel_id=7, translator=_Translator(), mapping=m)
    b.hooks = [_Webhook(1), _Webhook(2)]

    async def _get_webhook():
        if b._webhook is None:
            b._webhook = b.hooks.pop(0)
        return b._webhook

    b._get_webhook = _get_webhook
    yield b
    await m.close()


async def test_deleted_webhook_is_recreated_once(bot):
    bot.hooks[0].fail_send = 1
    msg = _Message(10, "안녕하세요")
    await bot.on_message(msg)
    assert bot._webhook.id == 2 and bot._webhook.sent == ["T:안녕하세요"]
    row = await bot.mapping.lookup(10)
    assert row.trans_ids == [1001]
    assert msg.reactions == []


async def test_other_http_error_adds_warning_reaction(bot):
    async def _boom(*a, **kw):
        raise _http_error(discord.Forbidden, 403)

    bot.hooks[0].send = _boom
    msg = _Message(11, "안녕하세요")
    await bot.on_message(msg)
    assert msg.reactions == ["⚠️"]


async def test_quota_reported_once_per_hour(bot, monkeypatch):
    captured = []
    monkeypatch.setattr(client_mod.sentry_sdk, "capture_exception", captured.append)
    bot.translator = _Translator(QuotaExceeded("quota"))
    await bot.on_message(_Message(12, "하나"))
    await bot.on_message(_Message(13, "둘"))
    assert len(captured) == 1


def _edit_payload(mid, content):
    return SimpleNamespace(channel_id=7, message_id=mid, data={"content": content})


def _channel_with(msg):
    async def fetch_message(mid):
        return msg
    return SimpleNamespace(fetch_message=fetch_message)


async def test_edit_with_same_content_is_ignored(bot):
    await bot.mapping.add(MapRow(orig_id=20, trans_id=30, channel_id=7, author_id=42,
                                 direction="KO>JA", orig_text="안녕", trans_ids=[30]))
    bot.translator = _Translator(RuntimeError("must not translate"))
    await bot.on_raw_message_edit(_edit_payload(20, "안녕"))


async def test_edit_to_untranslatable_deletes_all_chunks(bot):
    await bot.mapping.add(MapRow(orig_id=21, trans_id=31, channel_id=7, author_id=42,
                                 direction="KO>JA", orig_text="안녕", trans_ids=[31, 32]))
    bot.get_channel = lambda cid: _channel_with(_Message(21, "gg"))
    await bot.on_raw_message_edit(_edit_payload(21, "gg"))
    assert bot._webhook.deleted == [31, 32]
    assert await bot.mapping.lookup(21) is None


async def test_edit_updates_every_chunk_and_trims_extra(bot):
    await bot.mapping.add(MapRow(orig_id=22, trans_id=33, channel_id=7, author_id=42,
                                 direction="KO>JA", orig_text="안녕", trans_ids=[33, 34]))
    bot.get_channel = lambda cid: _channel_with(_Message(22, "반가워"))
    await bot.on_raw_message_edit(_edit_payload(22, "반가워"))
    assert bot._webhook.edited == [(33, "T:반가워")]
    assert bot._webhook.deleted == [34]
    row = await bot.mapping.lookup(22)
    assert row.trans_ids == [33] and row.orig_text == "반가워"


async def test_delete_removes_every_chunk(bot):
    await bot.mapping.add(MapRow(orig_id=23, trans_id=35, channel_id=7, author_id=42,
                                 direction="KO>JA", trans_ids=[35, 36, 37]))
    await bot.on_raw_message_delete(SimpleNamespace(channel_id=7, message_id=23))
    assert bot._webhook.deleted == [35, 36, 37]
    assert await bot.mapping.lookup(23) is None
