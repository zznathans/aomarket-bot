"""Top-level `!settings` admin command -- deliberately separate from the
`market`/`mkt` namespace in market/commands.py so it never passes through
that module's `Enabled` gate: an admin locked out by a disabled Market
module must still be able to re-enable it from in-game.
"""

import re

from aomarket.auth.service import AuthService
from aomarket.db.settings_repo import SettingValue, UnknownSettingError
from aomarket.market import rendering
from aomarket.market.service import MarketService

_ADMIN_PATTERNS = {
    "settings_set": re.compile(r"^!settings\s+([A-Za-z][A-Za-z0-9_]*)\s+(\S.*)$", re.IGNORECASE),
    "settings_get": re.compile(r"^!settings\s+([A-Za-z][A-Za-z0-9_]*)\s*$", re.IGNORECASE),
    "settings_list": re.compile(r"^!settings\s*$", re.IGNORECASE),
}


async def handle_admin_command(service: MarketService, auth: AuthService, player: str, msg: str) -> str | None:
    """Returns None if `msg` isn't a recognized admin command, or if the
    sender isn't an admin -- callers should treat None as "not handled" and
    fall through to the normal market-command dispatch, so non-admins get
    the ordinary reply (or none) with zero indication this command exists.
    """
    for name, pattern in _ADMIN_PATTERNS.items():
        match = pattern.match(msg)
        if not match:
            continue
        if not await auth.is_admin_player(player):
            return None
        try:
            return await _dispatch(service, name, match)
        except UnknownSettingError as exc:
            return f"Unknown setting {exc.args[0]!r}. Try '!settings' to list valid keys."
    return None


async def _dispatch(service: MarketService, name: str, match: re.Match) -> str:
    if name == "settings_set":
        key, raw_value = match.group(1), match.group(2).strip()
        try:
            value = await _coerce_setting_value(service, key, raw_value)
        except ValueError as exc:
            return str(exc)
        await service.settings.set(key, value)
        new_value = await service.settings.get(key)
        return f"{key} = {new_value!r}"

    if name == "settings_get":
        value = await service.settings.get(match.group(1))
        return f"{match.group(1)} = {value!r}"

    if name == "settings_list":
        return rendering.render_settings_list(await service.settings.all())

    raise AssertionError(f"unhandled admin command pattern {name!r}")


async def _coerce_setting_value(service: MarketService, key: str, raw: str) -> SettingValue:
    """Coerces raw chat text against the *current* stored type of `key`
    (read via SettingsRepo.get(), not DEFAULT_SETTINGS, so this stays
    correct even if a key's type is ever migrated). Raises ValueError with
    a chat-friendly message on bad input; UnknownSettingError from get()
    propagates to the caller unchanged.
    """
    current = await service.settings.get(key)  # UnknownSettingError propagates
    if isinstance(current, bool):  # must precede the int check -- bool is an int subclass
        lowered = raw.strip().lower()
        if lowered in ("true", "on", "yes", "1"):
            return True
        if lowered in ("false", "off", "no", "0"):
            return False
        raise ValueError(f"{raw!r} is not a valid bool for {key} (use true/false)")
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            raise ValueError(f"{raw!r} is not a valid integer for {key}") from None
    if isinstance(current, float):
        try:
            return float(raw)
        except ValueError:
            raise ValueError(f"{raw!r} is not a valid number for {key}") from None
    return raw
