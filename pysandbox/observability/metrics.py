"""Prometheus metrics for sandbox and plugin health."""

from prometheus_client import Counter, Gauge, Histogram

SANDBOX_COUNT = Gauge(
    "pysb_sandboxes_total",
    "Total sandboxes by status",
    ["status"],
)

PLUGIN_COUNT = Gauge(
    "pysb_plugins_total",
    "Total plugins installed by type",
    ["type"],
)

INSTALL_DURATION = Histogram(
    "pysb_plugin_install_seconds",
    "Plugin install duration",
    ["plugin_id"],
    buckets=[1, 5, 10, 20, 30, 60, 90, 120],
)

INSTALL_ERRORS = Counter(
    "pysb_plugin_install_errors",
    "Plugin install failures",
    ["plugin_id", "step"],
)

HEALTH_STATUS = Gauge(
    "pysb_plugin_health",
    "Plugin health status (1=healthy, 0=unhealthy)",
    ["sandbox", "plugin"],
)

AGENT_TASKS = Counter(
    "pysb_agent_tasks_total",
    "Agent task executions",
    ["sandbox", "status"],
)

DNS_LOOKUPS = Counter(
    "pysb_dns_lookups_total",
    "DNS lookup count",
    ["sandbox", "result"],
)
