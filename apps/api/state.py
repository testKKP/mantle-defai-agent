"""Runtime mutable state shared across modules."""

# Data aggregator (initialized in lifespan)
data_aggregator = None
aggregator_scheduler = None

# Unified DB refresh scheduler
_unified_refresh_task = None
_unified_refresh_running = False

def set_unified_refresh_running(value: bool) -> None:
    global _unified_refresh_running
    _unified_refresh_running = value


# Trend analysis scheduler
trend_scheduler = None
