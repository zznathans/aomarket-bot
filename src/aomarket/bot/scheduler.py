"""Two long-running asyncio tasks: poll and auto-track cycles.

Ported from Market.php's Market-Poll/Market-AutoTrack timers (Market.php:93-
121, 1438-1448) as plain asyncio.sleep loops rather than a persisted-timer
table -- re-reads its interval setting every cycle (so a setting change
applies without a restart) and never lets one bad cycle kill the loop.
"""

import asyncio
from datetime import UTC, datetime

from aomarket.logging import get_logger

log = get_logger(__name__)


async def poll_loop(bot: "MarketBot") -> None:  # noqa: F821
    while not bot._stopping:  # noqa: SLF001
        try:
            async with bot.make_service() as service:
                interval_minutes = await service.settings.get_int("PollIntervalMinutes")
                interval = max(60, 60 * interval_minutes)
                await service.poll_market()
                bot.last_poll_at = datetime.now(UTC)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("poll_loop_cycle_failed")
            interval = 60
        await asyncio.sleep(interval)


async def autotrack_loop(bot: "MarketBot") -> None:  # noqa: F821
    # Startup catch-up: if the last successful resync is staler than the
    # configured interval, run immediately rather than waiting for the next tick.
    try:
        async with bot.make_service() as service:
            if await service.settings.get_bool("AutoTrackEnabled"):
                interval_minutes = await service.settings.get_int("AutoTrackIntervalMinutes")
                interval = max(60, 60 * interval_minutes)
                last_sync = await service.settings.get_int("AutoTrackLastSync")
                if datetime.now(UTC).timestamp() - last_sync >= interval:
                    await service.sync_top_traded_items()
                    bot.last_autotrack_at = datetime.now(UTC)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("autotrack_startup_catchup_failed")

    while not bot._stopping:  # noqa: SLF001
        try:
            async with bot.make_service() as service:
                interval_minutes = await service.settings.get_int("AutoTrackIntervalMinutes")
                interval = max(60, 60 * interval_minutes)
        except Exception:
            log.exception("autotrack_loop_interval_read_failed")
            interval = 60

        await asyncio.sleep(interval)

        try:
            async with bot.make_service() as service:
                if await service.settings.get_bool("AutoTrackEnabled"):
                    count = await service.settings.get_int("AutoTrackCount")
                    if count >= 1:
                        await service.sync_top_traded_items()
                        bot.last_autotrack_at = datetime.now(UTC)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("autotrack_loop_cycle_failed")
