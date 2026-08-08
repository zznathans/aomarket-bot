"""In-game `market`/`mkt` command dispatch. Regex sub-dispatch mirrors
Market.php::command_handler()'s ordering (most-specific pattern first) --
calls straight into MarketService (the same methods api/routes/*.py calls)
and renders results via rendering.py. MarketService raises typed errors;
this layer's only job is turning those into chat-friendly text.
"""

import re

from aomarket.market import rendering
from aomarket.market.errors import (
    AlreadyRegisteredError,
    AlreadyWatchingError,
    InvalidRangeError,
    MarketError,
    NotRegisteredError,
    NotWatchingError,
    SubscriptionLimitError,
    UnknownItemError,
)
from aomarket.market.service import MarketService

_PREFIX = r"^(?:market|mkt)\s+"

_PATTERNS = {
    "register": re.compile(_PREFIX + r"register\s*$", re.IGNORECASE),
    "unregister": re.compile(_PREFIX + r"unregister(?:\s+(confirm))?\s*$", re.IGNORECASE),
    "untrack_all": re.compile(_PREFIX + r"untrack\s+all(?:\s+(confirm))?\s*$", re.IGNORECASE),
    "status_details": re.compile(_PREFIX + r"status\s+details\s*$", re.IGNORECASE),
    "status": re.compile(_PREFIX + r"status\s*$", re.IGNORECASE),
    "watchlist": re.compile(_PREFIX + r"watchlist\s*$", re.IGNORECASE),
    "user_stats": re.compile(_PREFIX + r"user\s+stats\s*(.*)$", re.IGNORECASE),
    "filter_price": re.compile(_PREFIX + r"filter\s+price\s+([0-9]+)\s+(.+)$", re.IGNORECASE),
    "filter_ql": re.compile(_PREFIX + r"filter\s+ql\s+([0-9]+)\s+(.+)$", re.IGNORECASE),
    "filter_clear": re.compile(_PREFIX + r"filter\s+clear\s+([0-9]+)\s*$", re.IGNORECASE),
    "filter_show": re.compile(_PREFIX + r"filter\s+([0-9]+)\s*$", re.IGNORECASE),
    "unwatch_all": re.compile(_PREFIX + r"unwatch\s+all(?:\s+(confirm))?\s*$", re.IGNORECASE),
    "unwatch_bulk": re.compile(_PREFIX + r"unwatch\s+([0-9]+(?:[\s,]+[0-9]+)+)\s*$", re.IGNORECASE),
    "unwatch": re.compile(_PREFIX + r"unwatch\s+([0-9]+)\s*$", re.IGNORECASE),
    "watch_aoid": re.compile(_PREFIX + r"watch\s+([0-9]+)\s*$", re.IGNORECASE),
    "watch_search": re.compile(_PREFIX + r"watch\s+(.+)$", re.IGNORECASE),
    "overview": re.compile(_PREFIX + r"([0-9]+)\s*$", re.IGNORECASE),
    "search": re.compile(_PREFIX + r"(.+)$", re.IGNORECASE),
}


async def handle_command(service: MarketService, player: str, msg: str) -> str:
    if not await service.settings.get_bool("Enabled"):
        return "The Market module is currently disabled."

    for name, pattern in _PATTERNS.items():
        match = pattern.match(msg)
        if not match:
            continue
        try:
            return await _dispatch(service, player, name, match)
        except MarketError as exc:
            return _format_error(exc)

    return (
        "Usage: market <item name> | market <aoid> | market status | market register | "
        "market watch <item> | market unwatch <aoid> | market watchlist | market help"
    )


async def _dispatch(service: MarketService, player: str, name: str, match: re.Match) -> str:
    if name == "register":
        await service.register(player)
        return "You're registered with the Market module. Try 'market watch <item>' to build a watchlist."

    if name == "unregister":
        if not (match.group(1) and match.group(1).lower() == "confirm"):
            return "This cannot be undone. Confirm with 'market unregister confirm'."
        removed = await service.unregister(player)
        return f"Unregistered. Removed {removed} watchlist item(s)."

    if name == "untrack_all":
        if not (match.group(1) and match.group(1).lower() == "confirm"):
            return "This cannot be undone. Confirm with 'market untrack all confirm'."
        cleared = await service.untrack_all()
        return f"Cleared {cleared} tracked item(s)."

    if name == "status_details":
        rows = await service.status_details()
        return rendering.render_status_summary(await service.status_summary()) + f"\n{len(rows)} item(s) tracked."

    if name == "status":
        return rendering.render_status_summary(await service.status_summary())

    if name == "watchlist":
        rows = await service.list_watchlist(player)
        return rendering.render_watchlist(rows)

    if name == "user_stats":
        target = match.group(1).strip() or player
        stats = await service.user_stats(target)
        if stats is None:
            return f"{target} has no recorded Market activity."
        return rendering.render_user_stats(target, stats)

    if name == "filter_price":
        aoid, spec = int(match.group(1)), match.group(2).strip()
        await service.set_price_filter(player, aoid, spec)
        sub = await service.get_filter(player, aoid)
        return "Price filter updated. " + rendering.describe_filter(
            sub.min_price, sub.max_price, sub.min_ql, sub.max_ql
        )

    if name == "filter_ql":
        aoid, spec = int(match.group(1)), match.group(2).strip()
        await service.set_ql_filter(player, aoid, spec)
        sub = await service.get_filter(player, aoid)
        return "QL filter updated. " + rendering.describe_filter(
            sub.min_price, sub.max_price, sub.min_ql, sub.max_ql
        )

    if name == "filter_clear":
        aoid = int(match.group(1))
        await service.clear_filter(player, aoid)
        return "Filter cleared - you'll be notified of every new order again."

    if name == "filter_show":
        aoid = int(match.group(1))
        sub = await service.get_filter(player, aoid)
        return rendering.describe_filter(sub.min_price, sub.max_price, sub.min_ql, sub.max_ql)

    if name == "unwatch_all":
        if not (match.group(1) and match.group(1).lower() == "confirm"):
            return "This cannot be undone. Confirm with 'market unwatch all confirm'."
        count = await service.unsubscribe_all(player)
        return f"Stopped watching all {count} item(s)."

    if name == "unwatch_bulk":
        aoids = [int(a) for a in re.split(r"[\s,]+", match.group(1).strip())]
        removed, not_watched = await service.unsubscribe_bulk(player, aoids)
        parts = []
        if removed:
            parts.append(f"Stopped watching {len(removed)} item(s): {', '.join(map(str, sorted(removed)))}.")
        if not_watched:
            parts.append(f"Not on your watchlist: {', '.join(map(str, sorted(not_watched)))}.")
        return "\n".join(parts)

    if name == "unwatch":
        aoid = int(match.group(1))
        deleted = await service.unsubscribe(player, aoid)
        return f"Stopped watching aoid {aoid}." if deleted else f"You weren't watching aoid {aoid}."

    if name == "watch_aoid":
        aoid = int(match.group(1))
        item = await service.subscribe(player, aoid)
        return f"You're now watching {item.name} (QL{item.ql}) - you'll get a tell when a new order shows up."

    if name == "watch_search":
        items, _total = await service.aodb.search_items(match.group(1).strip())
        return rendering.render_search_results(items)

    if name == "overview":
        aoid = int(match.group(1))
        item = await service.aodb.get_item(aoid)
        if item is None:
            return f"Unknown item ID {aoid}. Try 'market <item name>' to search first."
        await service.watch_item(aoid, item.name, item.ql, item.icon)
        orders = await service.gmi.get_orders(aoid)
        return rendering.render_overview(item.name, aoid, item.ql, orders)

    if name == "search":
        items, _total = await service.aodb.search_items(match.group(1).strip())
        return rendering.render_search_results(items)

    raise AssertionError(f"unhandled command pattern {name!r}")


def _format_error(exc: MarketError) -> str:
    if isinstance(exc, UnknownItemError):
        return f"Unknown item ID {exc.aoid}. Try 'market <item name>' to search first."
    if isinstance(exc, NotRegisteredError):
        return "You need to register first - try 'market register'."
    if isinstance(exc, AlreadyRegisteredError):
        return "You're already registered."
    if isinstance(exc, AlreadyWatchingError):
        return f"You're already watching aoid {exc.aoid}."
    if isinstance(exc, NotWatchingError):
        return f"You're not watching aoid {exc.aoid} - try 'market watch {exc.aoid}' first."
    if isinstance(exc, SubscriptionLimitError):
        return f"You're already watching the maximum of {exc.limit} item(s)."
    if isinstance(exc, InvalidRangeError):
        return f"Couldn't parse range {str(exc)!r}."
    return str(exc)
