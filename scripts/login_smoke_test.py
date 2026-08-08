"""Manual, opt-in smoke test: log into the real AO chat server and confirm
the handshake completes (LOGIN_SEED -> LOGIN_REQUEST -> LOGIN_CHARLIST ->
LOGIN_SELECT -> LOGIN_OK). No game-side assertions beyond that.

Usage:
    AO_LOGIN=... AO_PASSWORD=... AO_CHARACTER=... python3 scripts/login_smoke_test.py

This is the authoritative bit-exactness check for the crypto/packet port
(see aochat/crypto.py's module docstring) -- there is no PHP interpreter
available in the dev environment to cross-check against BeBot's original
AoChat.php directly, so a successful real login is the real verification.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from aomarket.aochat.client import AOChatClient  # noqa: E402
from aomarket.logging import configure_logging, get_logger  # noqa: E402

log = get_logger(__name__)


async def main() -> None:
    configure_logging("INFO")

    login = os.environ["AO_LOGIN"]
    password = os.environ["AO_PASSWORD"]
    character = os.environ["AO_CHARACTER"]
    host = os.environ.get("AO_CHAT_SERVER", "chat.d1.funcom.com")
    port = int(os.environ.get("AO_CHAT_PORT", "7105"))

    client = AOChatClient(host=host, port=port, username=login, password=password, character_name=character)

    log.info("connecting", host=host, port=port)
    await client.login()
    log.info("login_successful", character=client.character)

    await client._conn.close()  # noqa: SLF001


if __name__ == "__main__":
    asyncio.run(main())
