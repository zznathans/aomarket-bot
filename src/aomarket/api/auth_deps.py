"""API key enforcement for write routes. Kept separate from deps.py (which
is infra-only plumbing: sessions/service/bot-bridge) since auth is a
distinct, security-sensitive concern worth isolating with its own tests.
"""

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from aomarket.api.deps import get_db_session
from aomarket.auth.service import ApiKeyPrincipal, AuthService
from aomarket.db.api_key_repo import ApiKeyRepo
from aomarket.db.market_repo import MarketRepo

API_KEY_HEADER = "X-Api-Key"


async def get_auth_service(request: Request, session: AsyncSession = Depends(get_db_session)) -> AuthService:
    return AuthService(
        repo=ApiKeyRepo(session),
        market_repo=MarketRepo(session),
        owner_character=request.app.state.config.ao_owner_character,
    )


async def _authenticate(x_api_key: str | None, auth: AuthService) -> ApiKeyPrincipal:
    if not x_api_key:
        raise HTTPException(status_code=401, detail=f"missing {API_KEY_HEADER} header")
    principal = await auth.authenticate(x_api_key)
    if principal is None:
        raise HTTPException(status_code=401, detail="invalid or revoked API key")
    return principal


async def require_admin_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    auth: AuthService = Depends(get_auth_service),
) -> ApiKeyPrincipal:
    principal = await _authenticate(x_api_key, auth)
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="admin API key required")
    return principal


async def require_player_key(
    player: str,
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    auth: AuthService = Depends(get_auth_service),
) -> ApiKeyPrincipal:
    """`player` is bound from the route's own {player} path parameter --
    FastAPI resolves a dependency's parameters against the same path/
    query/body rules as the route handler itself, matched by name."""
    principal = await _authenticate(x_api_key, auth)
    if not principal.is_admin and principal.player != player:
        raise HTTPException(status_code=403, detail="API key is not scoped to this player")
    return principal
