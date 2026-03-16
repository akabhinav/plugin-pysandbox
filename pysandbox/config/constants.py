"""Platform-wide constants."""

# Naming constraints
PLUGIN_NAME_MIN_LENGTH = 3
PLUGIN_NAME_MAX_LENGTH = 40
PLUGIN_NAME_PATTERN = r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$"

# Reserved names that cannot be used as plugin instance names
RESERVED_NAMES = frozenset({"agent", "dns", "api", "engine", "sandbox", "system"})

# Docker label keys
LABEL_SANDBOX_ID = "pysandbox.sandbox_id"
LABEL_PLUGIN_ID = "pysandbox.plugin_id"
LABEL_PLUGIN_NAME = "pysandbox.plugin_name"

# Health check defaults
DEFAULT_HEALTH_INTERVAL_SEC = 5
DEFAULT_HEALTH_TIMEOUT_SEC = 3
DEFAULT_HEALTH_RETRIES = 10

# Plugin categories
VALID_CATEGORIES = frozenset({
    "databases", "messaging", "cloud", "runtime", "monitoring", "search",
})
