"""AuthService: API key issuance and verification. No knowledge of chat or
HTTP -- callers (the `apikey` chat commands, the API's auth dependencies)
adapt its typed results to their own presentation. A separate concern from
MarketService (security/identity plumbing, not market business logic),
kept in its own package the same way aochat/aodb/gmi are split out.
"""

import hashlib
import secrets
from dataclasses import dataclass

from aomarket.db.api_key_repo import ApiKeyRepo
from aomarket.db.market_repo import MarketRepo
from aomarket.db.models import ApiKey

_TOKEN_PREFIX = "aomk_"
_PREFIX_LENGTH = 12
# PBKDF2 iteration count. Tokens are already 192 bits of randomness (never
# user-chosen), so this isn't defending against a weak-input brute force
# the way password hashing is -- it's PBKDF2-HMAC-SHA256 rather than a
# bare hashlib.sha256() specifically to satisfy CodeQL's
# py/weak-sensitive-data-hashing check (which flags any fast hash applied
# to anything it classifies as credential-like) and as cheap
# defense-in-depth against a stolen-database brute force.
_PBKDF2_ITERATIONS = 100_000


@dataclass(frozen=True)
class ApiKeyPrincipal:
    player: str
    is_admin: bool


@dataclass
class AuthService:
    repo: ApiKeyRepo
    market_repo: MarketRepo
    # Player always treated as admin, regardless of MarketUser.is_admin --
    # bootstraps the first admin. Empty disables owner-bootstrap admin.
    owner_character: str = ""
    # Mixed into the PBKDF2 hash as the salt/pepper -- see AppConfig.api_key_pepper.
    pepper: str = ""

    async def generate_key(self, player: str) -> str:
        """Auto-registers `player` if not already a MarketUser (mirrors the
        chicken-and-egg handling :register already has to deal with),
        revokes any existing active key(s), mints and stores a new one, and
        returns the raw token -- the only time it's ever visible."""
        if not await self.market_repo.is_registered(player):
            await self.market_repo.register(player)
        await self.repo.revoke_all_for_player(player)
        raw = _generate_token()
        await self.repo.create(player, self._hash(raw), _prefix(raw))
        return raw

    async def revoke_keys(self, player: str) -> int:
        return await self.repo.revoke_all_for_player(player)

    async def list_keys(self, player: str) -> list[ApiKey]:
        return await self.repo.list_for_player(player)

    async def authenticate(self, raw_token: str) -> ApiKeyPrincipal | None:
        key = await self.repo.get_by_hash(self._hash(raw_token))
        if key is None:
            return None
        await self.repo.touch_last_used(key.id)
        is_admin = key.player == self.owner_character if self.owner_character else False
        if not is_admin:
            user = await self.market_repo.get_user(key.player)
            is_admin = bool(user and user.is_admin)
        return ApiKeyPrincipal(player=key.player, is_admin=is_admin)

    def _hash(self, raw: str) -> str:
        # A constant (not per-key) salt/pepper is a deliberate simplification:
        # this is a lookup-by-hash scheme (unlike password auth, which looks
        # up by username *then* verifies against that row's own salt), and
        # the 192 bits of entropy in every token already makes rainbow-table
        # precomputation infeasible regardless of per-row salting.
        return hashlib.pbkdf2_hmac("sha256", raw.encode(), self.pepper.encode(), _PBKDF2_ITERATIONS).hex()


def _generate_token() -> str:
    return f"{_TOKEN_PREFIX}{secrets.token_urlsafe(24)}"


def _prefix(raw: str) -> str:
    return raw[:_PREFIX_LENGTH]
