import asyncio
import json
import logging
import os

import sentry_sdk
from dotenv import load_dotenv

from bot.client import StellaBot
from bot.mapping import MessageMap
from bot.translator import DeepLClient

_RECONNECT_LOGGERS = ("discord.client", "discord.gateway")
_NOISE_EXC_NAMES = ("TimeoutError", "WSServerHandshakeError")


def _sentry_before_send(event, hint):
    """discord.py 재연결 중 일시적 네트워크 에러는 Sentry로 보내지 않는다."""
    if event.get("logger") not in _RECONNECT_LOGGERS:
        return event
    exc_info = hint.get("exc_info")
    if exc_info:
        name = type(exc_info[1]).__name__
        if name in _NOISE_EXC_NAMES or name.startswith("ClientConnector"):
            return None
    message = (event.get("logentry") or {}).get("message") or ""
    if message.startswith("Attempting a reconnect"):
        return None
    return event


async def main():
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    dsn = os.getenv("SENTRY_DSN")
    if dsn:
        sentry_sdk.init(dsn=dsn, environment="production", before_send=_sentry_before_send)

    mapping = MessageMap()
    os.makedirs("data", exist_ok=True)
    await mapping.open("data/stella.db")
    glossary_id = None
    if os.path.exists("config/glossary_ids.json"):
        with open("config/glossary_ids.json") as f:
            glossary_id = json.load(f)["glossary_id"]
    translator = DeepLClient(os.environ["DEEPL_API_KEY"], glossary_id=glossary_id)

    bot = StellaBot(
        channel_id=int(os.environ["CHANNEL_ID"]),
        translator=translator,
        mapping=mapping,
        allow_bots=os.getenv("ALLOW_BOT_MESSAGES") == "1",
    )
    try:
        await bot.start(os.environ["DISCORD_TOKEN"])
    finally:
        await translator.close()
        await mapping.close()


if __name__ == "__main__":
    asyncio.run(main())
