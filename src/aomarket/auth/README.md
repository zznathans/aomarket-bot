# auth

API key issuance and verification — a separate concern from
[`market/`](../market/README.md)'s business logic, kept in its own
package the same way [`aochat/`](../aochat/README.md)/
[`aodb/`](../aodb/README.md)/[`gmi/`](../gmi/README.md) are split out.

## Files

- **`service.py`** — `AuthService`, the single entry point both the
  `apikey` chat commands ([`market/commands.py`](../market/README.md))
  and the API's auth dependencies
  ([`api/auth_deps.py`](../api/README.md)) call into.
  - `generate_key(player)` — auto-registers `player` if needed, revokes
    any existing active key(s) (one active key per player, enforced here
    rather than at the DB level), mints a new `aomk_<random>` token
    (192 bits of randomness — never user-chosen), stores its
    PBKDF2-HMAC-SHA256 hash (never the raw token; `AppConfig.api_key_pepper`
    is mixed in as a constant server-side pepper, same for every key — a
    per-key salt isn't meaningful here since this is a lookup-by-hash
    scheme, and the entropy in every token already makes rainbow-table
    precomputation infeasible regardless of salting) plus a short
    clear-text prefix (`ApiKeyRepo`, [`db/`](../db/README.md)) for
    display/audit, and returns the raw token — the only time it's ever
    visible.
  - `authenticate(raw_token)` — hash lookup, `None` if missing/revoked.
    Resolves `ApiKeyPrincipal.is_admin` to `True` if the key's player
    matches `AppConfig.ao_owner_character`, or if `MarketUser.is_admin`
    is set. Updates `last_used_at` on success.
  - `revoke_keys(player)` / `list_keys(player)`.

## How it's used

- **Chat**: `market apikey generate` / `revoke [confirm]` / `list` in
  [`market/commands.py`](../market/README.md), delivered via the same
  tell mechanism as every other chat reply — the raw key text is just
  part of the returned reply string, shown once.
  [`bot/runner.py`](../bot/README.md)'s `MarketBot.make_auth_service()`
  builds an `AuthService` per tell the same way `make_service()` builds a
  `MarketService`.
- **HTTP**: [`api/auth_deps.py`](../api/README.md)'s `require_player_key`
  / `require_admin_key` FastAPI dependencies call `authenticate()` against
  the `X-Api-Key` header on every write route.

Key issuance deliberately only happens through chat, not an open HTTP
endpoint — the chat bridge is the only place a player's identity is
actually verified (the AO chat server tells the bot who it's talking to).
A key generated for a player is scoped to whatever identity the bot
resolved for them at that moment: their name once
[`AOCP_CLIENT_NAME`](../aochat/README.md) has arrived, otherwise their
numeric character id as a fallback.
