from os import getenv

lightning_address_enabled = getenv(
    "ZAPGOALS_ENABLE_LIGHTNING_ADDRESS", "false"
).lower() in {"1", "true", "yes"}

builtin_scheduler_enabled = getenv("ZAPGOALS_BUILTIN_SCHEDULER", "false").lower() in {
    "1",
    "true",
    "yes",
}

builtin_scheduler_interval_seconds = int(
    getenv("ZAPGOALS_SCHEDULER_INTERVAL_SECONDS", "3600")
)
