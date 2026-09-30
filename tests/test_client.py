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
    assert row.trans_id == 1001
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
