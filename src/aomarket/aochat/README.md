# aochat

The Anarchy Online chat protocol client: raw socket framing, the DH+TEA
login handshake, and an asyncio-based session used by the bot to receive
tells and send replies.

## Files

- **`protocol.py`** — `AOChatConnection`: the raw TCP transport. Connects,
  reads one length-prefixed packet at a time, writes one packet at a
  time. No login or dispatch logic lives here.
- **`packet.py`** — Packet type IDs and the (de)serialization schemas for
  the subset of the AO chat protocol this bot actually needs. Tells,
  privgroup messages, the login sequence, and `AOCP_CLIENT_NAME`
  (server-pushed id→name resolution, decoded but never requested by the
  client) are implemented — guild, duel, group chat, and friends/buddy
  list management are out of scope.
- **`crypto.py`** — Diffie-Hellman key exchange and TEA encryption used
  during login, as required by the AO chat server before it will accept
  `LOGIN_REQUEST`.
- **`client.py`** — `AOChatClient`: the high-level session. Drives the
  login sequence (`LOGIN_SEED` → `LOGIN_REQUEST` → `LOGIN_CHARLIST` →
  `LOGIN_SELECT` → `LOGIN_OK`), sends a keepalive ping every 60 seconds,
  dispatches inbound tells/privgroup messages to registered handlers, and
  maintains an id→name cache (`name_for_id()`) populated as
  `AOCP_CLIENT_NAME` packets arrive from the server — used to resolve a
  tell sender's actual character name rather than just their numeric id
  (see [`bot/README.md`](../bot/README.md)).
- **`types.py`** — Plain dataclasses for the parsed values handlers
  receive (`InboundTell`, `InboundPrivgroupMessage`, `BuddyStatus`,
  `CharacterInfo`).

## How it's used

[`bot/runner.py`](../bot/README.md) owns the single `AOChatClient`
instance for the process — one login, one character session, for the
lifetime of the bot thread. Inbound tells are routed to
[`market/commands.py`](../market/README.md) for command dispatch; replies
go back out over the same client.

If `AO_LOGIN`/`AO_PASSWORD`/`AO_CHARACTER` aren't set, this module is
never instantiated at all and the bot runs in API-only mode — see the
[package overview](../README.md) for how that decision is made.
