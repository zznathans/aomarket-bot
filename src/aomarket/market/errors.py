class MarketError(Exception):
    """Base for all typed errors MarketService raises; transports (API routes,
    chat commands) catch this and adapt it to their own response format."""


class MarketDisabledError(MarketError):
    pass


class UnknownItemError(MarketError):
    def __init__(self, aoid: int):
        super().__init__(f"unknown item aoid {aoid}")
        self.aoid = aoid


class AlreadyRegisteredError(MarketError):
    pass


class NotRegisteredError(MarketError):
    pass


class AlreadyWatchingError(MarketError):
    def __init__(self, aoid: int):
        super().__init__(f"already watching aoid {aoid}")
        self.aoid = aoid


class NotWatchingError(MarketError):
    def __init__(self, aoid: int):
        super().__init__(f"not watching aoid {aoid}")
        self.aoid = aoid


class SubscriptionLimitError(MarketError):
    def __init__(self, limit: int):
        super().__init__(f"subscription limit of {limit} reached")
        self.limit = limit


class InvalidRangeError(MarketError):
    pass


class NoActivityError(MarketError):
    pass
