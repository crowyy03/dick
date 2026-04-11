"""MVP in-process rate limiting (per process; resets on restart)."""

from __future__ import annotations

import time
from collections import defaultdict


class RegenerateRateLimiter:
    def __init__(self) -> None:
        self._last_ts: dict[int, float] = {}
        self._day_counts: dict[tuple[int, str], int] = defaultdict(int)
        self._day_window: dict[int, str] = {}

    def _day_key(self, user_id: int) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def check(self, user_id: int, cooldown_sec: int, max_per_day: int) -> tuple[bool, str | None]:
        now = time.time()
        day = self._day_key(user_id)
        if self._day_window.get(user_id) != day:
            self._day_window[user_id] = day
            self._day_counts[(user_id, day)] = 0

        last = self._last_ts.get(user_id)
        if last is not None and now - last < cooldown_sec:
            wait = int(cooldown_sec - (now - last)) + 1
            return False, (
                f"Слишком часто жмёшь обновить - подожди ещё {wait} сек. "
                f"Это не из вредности, так меньше хаоса на сервере."
            )

        if self._day_counts[(user_id, day)] >= max_per_day:
            return False, (
                "Слышь, на сегодня лимит обновлений исчерпан. "
                "Если ключ реально умер — напиши админу, он человечнее любого таймера)"
            )

        return True, None

    def register(self, user_id: int) -> None:
        now = time.time()
        self._last_ts[user_id] = now
        day = self._day_key(user_id)
        self._day_counts[(user_id, day)] += 1
