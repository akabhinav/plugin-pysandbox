"""Sandbox Templates — pre-configured sandbox blueprints for common stacks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SandboxTemplate:
    """A reusable sandbox blueprint with pre-configured plugins."""

    id: str
    name: str
    description: str
    category: str
    icon: str
    plugins: list[dict[str, Any]]
    tags: dict[str, str] = field(default_factory=dict)
    estimated_startup_seconds: int = 60


# Built-in templates
BUILTIN_TEMPLATES: dict[str, SandboxTemplate] = {}


def _register(template: SandboxTemplate) -> None:
    BUILTIN_TEMPLATES[template.id] = template


# ── Data Lakehouse ───────────────────────────────────────────────────────────
_register(SandboxTemplate(
    id="data-lakehouse",
    name="Data Lakehouse",
    description="Full data lakehouse with Spark compute, MinIO storage, Nessie catalog, and Dremio SQL analytics.",
    category="data",
    icon="🏠",
    plugins=[
        {"plugin_id": "minio", "name": "minio", "expose": True, "startup_order": 10},
        {"plugin_id": "nessie", "name": "nessie", "expose": True, "startup_order": 20},
        {"plugin_id": "spark", "name": "spark", "expose": True, "startup_order": 30,
         "config": {"workers": 2, "worker_cores": 2, "worker_memory": "1g"}},
        {"plugin_id": "dremio", "name": "dremio", "expose": True, "startup_order": 40},
    ],
    tags={"stack": "lakehouse", "template": "data-lakehouse"},
    estimated_startup_seconds=180,
))

# ── ML Pipeline ──────────────────────────────────────────────────────────────
_register(SandboxTemplate(
    id="ml-pipeline",
    name="ML Pipeline",
    description="Machine learning development with Jupyter notebooks, PostgreSQL storage, and MinIO for model artifacts.",
    category="data-science",
    icon="🤖",
    plugins=[
        {"plugin_id": "postgres", "name": "postgres", "expose": True, "startup_order": 10},
        {"plugin_id": "minio", "name": "minio", "expose": True, "startup_order": 20},
        {"plugin_id": "jupyter", "name": "jupyter", "expose": True, "startup_order": 30},
    ],
    tags={"stack": "ml", "template": "ml-pipeline"},
    estimated_startup_seconds=90,
))

# ── Microservices ────────────────────────────────────────────────────────────
_register(SandboxTemplate(
    id="microservices",
    name="Microservices Stack",
    description="Complete microservices dev environment with Kafka messaging, Redis caching, PostgreSQL, and full observability.",
    category="backend",
    icon="🔧",
    plugins=[
        {"plugin_id": "postgres", "name": "postgres", "expose": True, "startup_order": 10},
        {"plugin_id": "redis", "name": "redis", "expose": True, "startup_order": 10},
        {"plugin_id": "kafka", "name": "kafka", "expose": True, "startup_order": 20},
        {"plugin_id": "prometheus", "name": "prometheus", "expose": True, "startup_order": 30},
        {"plugin_id": "grafana", "name": "grafana", "expose": True, "startup_order": 40},
        {"plugin_id": "jaeger", "name": "jaeger", "expose": True, "startup_order": 40},
    ],
    tags={"stack": "microservices", "template": "microservices"},
    estimated_startup_seconds=120,
))

# ── Observability ────────────────────────────────────────────────────────────
_register(SandboxTemplate(
    id="observability",
    name="Observability Stack",
    description="Full observability with Prometheus metrics, Grafana dashboards, and Jaeger distributed tracing.",
    category="monitoring",
    icon="📊",
    plugins=[
        {"plugin_id": "prometheus", "name": "prometheus", "expose": True, "startup_order": 10},
        {"plugin_id": "grafana", "name": "grafana", "expose": True, "startup_order": 20},
        {"plugin_id": "jaeger", "name": "jaeger", "expose": True, "startup_order": 20},
    ],
    tags={"stack": "observability", "template": "observability"},
    estimated_startup_seconds=60,
))

# ── Event-Driven ─────────────────────────────────────────────────────────────
_register(SandboxTemplate(
    id="event-driven",
    name="Event-Driven Architecture",
    description="Event-driven stack with Kafka streaming, RabbitMQ messaging, and Redis for state management.",
    category="messaging",
    icon="📨",
    plugins=[
        {"plugin_id": "kafka", "name": "kafka", "expose": True, "startup_order": 10},
        {"plugin_id": "rabbitmq", "name": "rabbitmq", "expose": True, "startup_order": 10},
        {"plugin_id": "redis", "name": "redis", "expose": True, "startup_order": 10},
    ],
    tags={"stack": "event-driven", "template": "event-driven"},
    estimated_startup_seconds=90,
))

# ── Graph Analytics ──────────────────────────────────────────────────────────
_register(SandboxTemplate(
    id="graph-analytics",
    name="Graph Analytics",
    description="Graph database analytics with Neo4j and Jupyter for interactive exploration.",
    category="data-science",
    icon="🕸️",
    plugins=[
        {"plugin_id": "neo4j", "name": "neo4j", "expose": True, "startup_order": 10},
        {"plugin_id": "jupyter", "name": "jupyter", "expose": True, "startup_order": 20},
    ],
    tags={"stack": "graph", "template": "graph-analytics"},
    estimated_startup_seconds=60,
))

# ── Search & Analytics ───────────────────────────────────────────────────────
_register(SandboxTemplate(
    id="search-analytics",
    name="Search & Analytics",
    description="Full-text search and analytics with Elasticsearch, ClickHouse, and Grafana dashboards.",
    category="data",
    icon="🔍",
    plugins=[
        {"plugin_id": "elasticsearch", "name": "elasticsearch", "expose": True, "startup_order": 10},
        {"plugin_id": "clickhouse", "name": "clickhouse", "expose": True, "startup_order": 10},
        {"plugin_id": "grafana", "name": "grafana", "expose": True, "startup_order": 30},
    ],
    tags={"stack": "search", "template": "search-analytics"},
    estimated_startup_seconds=90,
))


class TemplateRegistry:
    """Manages sandbox templates — builtin + custom."""

    def __init__(self) -> None:
        self._custom: dict[str, SandboxTemplate] = {}

    def list_all(self) -> list[SandboxTemplate]:
        """List all templates (builtin + custom)."""
        all_templates = list(BUILTIN_TEMPLATES.values()) + list(self._custom.values())
        return sorted(all_templates, key=lambda t: t.name)

    def get(self, template_id: str) -> SandboxTemplate | None:
        return BUILTIN_TEMPLATES.get(template_id) or self._custom.get(template_id)

    def register(self, template: SandboxTemplate) -> None:
        """Register a custom template."""
        self._custom[template.id] = template

    def unregister(self, template_id: str) -> bool:
        """Unregister a custom template. Returns True if found."""
        return self._custom.pop(template_id, None) is not None
