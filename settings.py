from os import getenv

lightning_address_enabled = getenv(
    "ZAPGOALS_ENABLE_LIGHTNING_ADDRESS", "false"
).lower() in {"1", "true", "yes"}
