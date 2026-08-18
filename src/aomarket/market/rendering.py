"""Chat-text formatting for command replies. Plain text (no AO-specific
chatcmd()/make_blob()/itemref:// markup, which is an in-game-client-only
presentation layer with no meaning outside a live AO chat window).
"""

from aomarket.gmi.client import Orders
from aomarket.market.parsing import format_credits


def render_search_results(items) -> str:
    if not items:
        return "No searchable item(s) found corresponding to your keyword(s)"
    lines = [f"{i.name} QL{i.ql} [aoid {i.aoid}]" for i in items]
    return f"{len(items)} matching item(s):\n" + "\n".join(lines)


def render_overview(item_name: str, aoid: int, ql: int, orders: Orders | None) -> str:
    header = f":: {item_name} :: QL{ql} (aoid {aoid})"
    if orders is None:
        return f"{header}\n\nMarket data currently unavailable, please try again later."
    return f"{header}\n\n{render_summary(orders)}"


def render_summary(orders: Orders) -> str:
    lines = []
    if orders.sell_orders:
        best_sell = min(o.price for o in orders.sell_orders)
        lines.append(f"Best sell: {format_credits(best_sell)} ({len(orders.sell_orders)} sell order(s))")
    else:
        lines.append("No sell orders")
    if orders.buy_orders:
        best_buy = max(o.price for o in orders.buy_orders)
        lines.append(f"Best buy: {format_credits(best_buy)} ({len(orders.buy_orders)} buy order(s))")
    else:
        lines.append("No buy orders")
    return "\n".join(lines)


def render_watchlist(subscriptions) -> str:
    if not subscriptions:
        return "Your watchlist is empty. Try 'market watch <item>' to add one."
    lines = []
    for sub in subscriptions:
        filt = describe_filter(sub.min_price, sub.max_price, sub.min_ql, sub.max_ql)
        lines.append(f"aoid {sub.aoid} - {filt}")
    return f"{len(subscriptions)} item(s) watched:\n" + "\n".join(lines)


def describe_filter(min_price, max_price, min_ql, max_ql) -> str:
    if min_price is None and max_price is None and min_ql is None and max_ql is None:
        return "No filter set - you'll be notified of every new order."
    parts = []
    if min_price is not None or max_price is not None:
        lo = format_credits(min_price) if min_price is not None else "any"
        hi = format_credits(max_price) if max_price is not None else "any"
        parts.append(f"price {lo}-{hi}")
    if min_ql is not None or max_ql is not None:
        lo = min_ql if min_ql is not None else "any"
        hi = max_ql if max_ql is not None else "any"
        parts.append(f"QL {lo}-{hi}")
    return "Filter: " + ", ".join(parts)


def render_status_summary(summary: dict) -> str:
    return (
        f"Total tracked: {summary['total_tracked']} "
        f"(auto: {summary['auto_tracked']}, manual: {summary['manually_tracked']})\n"
        f"Auto-track: {'On' if summary['auto_track_enabled'] else 'Off'} "
        f"(target {summary['auto_track_count']} items)"
    )


def render_settings_list(settings: dict) -> str:
    if not settings:
        return "No settings found."
    lines = [f"{key} = {value!r}" for key, value in sorted(settings.items())]
    return f"{len(settings)} setting(s):\n" + "\n".join(lines)


def render_user_stats(player: str, stats: dict) -> str:
    lines = [
        f"Market activity: {player}",
        f"Total actions: {stats['total_actions']}",
        f"Active subscriptions: {stats['active_subscriptions']}",
        "",
    ]
    for action, count in stats["by_action"]:
        lines.append(f"{action}: {count}")
    return "\n".join(lines)
