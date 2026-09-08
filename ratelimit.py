from time import monotonic


class WindowRateLimiter:
    """Best-effort in-memory fixed-window rate limiter.

    Keys are independent per caller (e.g. "ip:goal_id"). State is kept per
    process, so deployments running multiple workers or instances get a
    limit multiplied by the worker count and should enforce stronger
    limits at the gateway.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, tuple[float, int]] = {}
        self._last_sweep = monotonic()

    def allow(self, key: str) -> bool:
        """Consume one slot for key, returning False when over the limit."""
        if self.limit <= 0:
            return True
        now = monotonic()
        self._sweep(now)
        window_start, count = self._hits.get(key, (now, 0))
        if now - window_start >= self.window_seconds:
            window_start, count = now, 0
        allowed = count < self.limit
        if allowed:
            count += 1
        self._hits[key] = (window_start, count)
        return allowed

    def _sweep(self, now: float) -> None:
        if now - self._last_sweep < self.window_seconds:
            return
        self._last_sweep = now
        self._hits = {
            key: entry
            for key, entry in self._hits.items()
            if now - entry[0] < self.window_seconds
        }
