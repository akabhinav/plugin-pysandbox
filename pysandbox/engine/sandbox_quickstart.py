"""Interactive Quickstart — per-template guided walkthroughs for developers.

Each quickstart is a series of steps that teach developers how to use
the sandbox by running real commands in the right order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class QuickstartStep:
    """A single step in a quickstart guide."""

    title: str
    description: str
    plugin: str  # which plugin tab/tool to use
    tool: str  # tool_name to execute
    params: dict[str, Any]  # pre-filled parameters
    expected_output: str  # hint about what to expect
    tip: str = ""  # optional pro-tip


@dataclass
class Quickstart:
    """A complete quickstart guide for a template."""

    template_id: str
    title: str
    description: str
    estimated_minutes: int
    steps: list[QuickstartStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "template_id": self.template_id,
            "title": self.title,
            "description": self.description,
            "estimated_minutes": self.estimated_minutes,
            "total_steps": len(self.steps),
            "steps": [
                {
                    "step": i + 1,
                    "title": s.title,
                    "description": s.description,
                    "plugin": s.plugin,
                    "tool": s.tool,
                    "params": s.params,
                    "expected_output": s.expected_output,
                    "tip": s.tip,
                }
                for i, s in enumerate(self.steps)
            ],
        }


# ── Quickstart Definitions ───────────────────────────────────────────────────

QUICKSTARTS: dict[str, Quickstart] = {}


def _register(qs: Quickstart) -> None:
    QUICKSTARTS[qs.template_id] = qs


_register(Quickstart(
    template_id="microservices",
    title="Build a Microservices Event Pipeline",
    description="Create a user, publish an event to Kafka, cache it in Redis, and trace it end-to-end.",
    estimated_minutes=5,
    steps=[
        QuickstartStep(
            title="Create a users table in PostgreSQL",
            description="Start by setting up your database schema.",
            plugin="postgres",
            tool="sql_execute",
            params={"query": "CREATE TABLE IF NOT EXISTS users (id serial PRIMARY KEY, name text, email text UNIQUE, created_at timestamp DEFAULT now())"},
            expected_output="Table created successfully",
            tip="PostgreSQL is already running with extensions uuid-ossp and pgcrypto loaded.",
        ),
        QuickstartStep(
            title="Insert your first user",
            description="Add a test user to the database.",
            plugin="postgres",
            tool="sql_execute",
            params={"query": "INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com') ON CONFLICT DO NOTHING"},
            expected_output="INSERT 0 1",
        ),
        QuickstartStep(
            title="Create a Kafka topic for user events",
            description="Set up the event stream for user lifecycle events.",
            plugin="kafka",
            tool="kafka_create_topic",
            params={"topic": "user-events", "partitions": 3, "replication_factor": 1},
            expected_output="Topic created",
            tip="3 partitions allows parallel consumption for higher throughput.",
        ),
        QuickstartStep(
            title="Publish a user.created event",
            description="Simulate your user service emitting an event after user creation.",
            plugin="kafka",
            tool="kafka_produce",
            params={"topic": "user-events", "message": "{\"type\": \"user.created\", \"user_id\": 1, \"name\": \"Alice\", \"email\": \"alice@example.com\"}"},
            expected_output="Message produced",
        ),
        QuickstartStep(
            title="Cache the user in Redis",
            description="Your consumer service reads the event and caches the user for fast lookups.",
            plugin="redis",
            tool="redis_set",
            params={"key": "user:1", "value": "{\"name\": \"Alice\", \"email\": \"alice@example.com\"}"},
            expected_output="OK",
        ),
        QuickstartStep(
            title="Verify the cached user",
            description="Confirm the cache is working by reading the user back.",
            plugin="redis",
            tool="redis_get",
            params={"key": "user:1"},
            expected_output='{"name": "Alice", ...}',
        ),
        QuickstartStep(
            title="Query the database to confirm",
            description="Verify the original data in PostgreSQL matches what's cached.",
            plugin="postgres",
            tool="sql_query",
            params={"query": "SELECT name, email FROM users WHERE email = 'alice@example.com'"},
            expected_output="Alice | alice@example.com",
            tip="You now have data flowing through all 3 services: Postgres -> Kafka -> Redis. Check Jaeger and Grafana for observability!",
        ),
    ],
))


_register(Quickstart(
    template_id="ml-pipeline",
    title="Build an ML Feature Pipeline",
    description="Create a dataset in PostgreSQL, upload training data to MinIO, and explore in Jupyter.",
    estimated_minutes=5,
    steps=[
        QuickstartStep(
            title="Create a features table",
            description="Define your ML feature schema in PostgreSQL.",
            plugin="postgres",
            tool="sql_execute",
            params={"query": "CREATE TABLE IF NOT EXISTS features (id serial PRIMARY KEY, user_id int, page_views int, session_duration float, purchases int, label int)"},
            expected_output="Table created",
        ),
        QuickstartStep(
            title="Insert training data",
            description="Add labeled training samples.",
            plugin="postgres",
            tool="sql_execute",
            params={"query": "INSERT INTO features (user_id, page_views, session_duration, purchases, label) VALUES (1, 50, 120.5, 3, 1), (2, 5, 10.0, 0, 0), (3, 80, 300.2, 7, 1), (4, 2, 5.5, 0, 0), (5, 45, 95.0, 2, 1)"},
            expected_output="INSERT 0 5",
        ),
        QuickstartStep(
            title="Verify your dataset",
            description="Check the data distribution with a quick query.",
            plugin="postgres",
            tool="sql_query",
            params={"query": "SELECT label, count(*) as count, avg(page_views)::int as avg_views, avg(session_duration)::int as avg_duration FROM features GROUP BY label ORDER BY label"},
            expected_output="Two rows showing label 0 and label 1 with stats",
            tip="Label 1 (converted users) have higher page views and session duration — your model should pick this up!",
        ),
        QuickstartStep(
            title="Check MinIO is ready for artifacts",
            description="Verify object storage is available for model artifacts.",
            plugin="minio",
            tool="s3_list",
            params={},
            expected_output="Bucket listing (may be empty)",
            tip="Open Jupyter from Quick Access and use boto3 to upload/download model files to MinIO!",
        ),
    ],
))


_register(Quickstart(
    template_id="event-driven",
    title="Build an Event-Driven Pipeline",
    description="Set up Kafka topics, publish/consume messages, and use Redis for state tracking.",
    estimated_minutes=4,
    steps=[
        QuickstartStep(
            title="Create an orders topic in Kafka",
            description="Set up the main event stream for order processing.",
            plugin="kafka",
            tool="kafka_create_topic",
            params={"topic": "orders", "partitions": 3, "replication_factor": 1},
            expected_output="Topic created",
        ),
        QuickstartStep(
            title="Publish an order event",
            description="Simulate an e-commerce order being placed.",
            plugin="kafka",
            tool="kafka_produce",
            params={"topic": "orders", "message": "{\"order_id\": 1001, \"product\": \"Laptop\", \"amount\": 999.99, \"status\": \"placed\"}"},
            expected_output="Message produced",
        ),
        QuickstartStep(
            title="Track order state in Redis",
            description="Your order processor reads the event and tracks state.",
            plugin="redis",
            tool="redis_set",
            params={"key": "order:1001:status", "value": "processing"},
            expected_output="OK",
        ),
        QuickstartStep(
            title="Check order state",
            description="Any service can quickly check the current order status.",
            plugin="redis",
            tool="redis_get",
            params={"key": "order:1001:status"},
            expected_output="processing",
            tip="Try the RabbitMQ management UI for a different messaging pattern — it supports routing, dead letters, and priorities.",
        ),
    ],
))


_register(Quickstart(
    template_id="data-lakehouse",
    title="Explore the Data Lakehouse",
    description="Upload data to MinIO, catalog with Nessie, and query with Spark and Dremio.",
    estimated_minutes=5,
    steps=[
        QuickstartStep(
            title="Verify MinIO storage",
            description="Check that object storage is ready for data files.",
            plugin="minio",
            tool="s3_list",
            params={},
            expected_output="Bucket listing",
        ),
        QuickstartStep(
            title="Check Nessie catalog branches",
            description="Verify the Iceberg catalog is running with a main branch.",
            plugin="nessie",
            tool="nessie_list_branches",
            params={},
            expected_output="main branch listed",
            tip="Nessie gives you Git-like version control for your data lake. Try creating a branch for experiments!",
        ),
        QuickstartStep(
            title="Run a Spark SQL query",
            description="Test that Spark can execute queries on the cluster.",
            plugin="spark",
            tool="spark_submit_sql",
            params={"query": "SELECT 'lakehouse_ready' AS status, current_timestamp() AS checked_at"},
            expected_output="lakehouse_ready with timestamp",
            tip="Open the Spark UI and Dremio from Quick Access to explore the full lakehouse visually!",
        ),
    ],
))


_register(Quickstart(
    template_id="graph-analytics",
    title="Build a Social Graph",
    description="Create person nodes, add relationships, and query the graph in Neo4j.",
    estimated_minutes=4,
    steps=[
        QuickstartStep(
            title="Create person nodes",
            description="Add people to the graph database.",
            plugin="neo4j",
            tool="cypher_query",
            params={"query": "CREATE (a:Person {name: 'Alice', role: 'Engineer'}), (b:Person {name: 'Bob', role: 'Manager'}), (c:Person {name: 'Charlie', role: 'Designer'}) RETURN a.name, b.name, c.name"},
            expected_output="Three person names returned",
        ),
        QuickstartStep(
            title="Add team relationships",
            description="Connect the people with reporting and collaboration edges.",
            plugin="neo4j",
            tool="cypher_query",
            params={"query": "MATCH (a:Person {name: 'Alice'}), (b:Person {name: 'Bob'}), (c:Person {name: 'Charlie'}) CREATE (a)-[:REPORTS_TO]->(b), (c)-[:REPORTS_TO]->(b), (a)-[:COLLABORATES_WITH]->(c) RETURN count(*) AS relationships"},
            expected_output="3 relationships created",
        ),
        QuickstartStep(
            title="Query the team structure",
            description="Find who reports to Bob.",
            plugin="neo4j",
            tool="cypher_query",
            params={"query": "MATCH (p:Person)-[:REPORTS_TO]->(m:Person {name: 'Bob'}) RETURN p.name AS team_member, p.role AS role"},
            expected_output="Alice (Engineer) and Charlie (Designer)",
            tip="Open Neo4j Browser from Quick Access to visualize the graph! Try MATCH (n) RETURN n to see everything.",
        ),
    ],
))


_register(Quickstart(
    template_id="search-analytics",
    title="Build a Search & Analytics Pipeline",
    description="Index documents in Elasticsearch and run analytics queries in ClickHouse.",
    estimated_minutes=4,
    steps=[
        QuickstartStep(
            title="Check Elasticsearch cluster health",
            description="Verify the search engine is ready.",
            plugin="elasticsearch",
            tool="es_cluster_health",
            params={},
            expected_output="Cluster status (green/yellow)",
        ),
        QuickstartStep(
            title="Create analytics events in ClickHouse",
            description="Set up a high-performance analytics table.",
            plugin="clickhouse",
            tool="clickhouse_query",
            params={"query": "CREATE TABLE IF NOT EXISTS page_views (ts DateTime DEFAULT now(), url String, user_id UInt32, duration_ms UInt32) ENGINE = MergeTree() ORDER BY ts"},
            expected_output="Table created",
        ),
        QuickstartStep(
            title="Insert sample analytics data",
            description="Add page view events for analysis.",
            plugin="clickhouse",
            tool="clickhouse_query",
            params={"query": "INSERT INTO page_views (url, user_id, duration_ms) VALUES ('/home', 1, 1500), ('/products', 2, 3200), ('/home', 3, 800), ('/checkout', 1, 5000), ('/products', 1, 2100)"},
            expected_output="Data inserted",
        ),
        QuickstartStep(
            title="Run an analytics query",
            description="Find the most popular pages.",
            plugin="clickhouse",
            tool="clickhouse_query",
            params={"query": "SELECT url, count() as views, avg(duration_ms) as avg_duration FROM page_views GROUP BY url ORDER BY views DESC"},
            expected_output="Pages ranked by view count",
            tip="ClickHouse handles billions of rows — try inserting more data and watch the query speed!",
        ),
    ],
))


_register(Quickstart(
    template_id="observability",
    title="Explore the Observability Stack",
    description="Check Prometheus metrics, verify Grafana dashboards, and inspect Jaeger traces.",
    estimated_minutes=3,
    steps=[
        QuickstartStep(
            title="Open Prometheus",
            description="Prometheus is collecting metrics from all services. Open it from Quick Access.",
            plugin="prometheus",
            tool="",
            params={},
            expected_output="Prometheus UI loads with targets",
            tip="Try querying 'up' in the Prometheus expression browser to see which targets are being scraped.",
        ),
        QuickstartStep(
            title="Open Grafana dashboards",
            description="Grafana connects to Prometheus for visualization. Default login: admin/admin.",
            plugin="grafana",
            tool="",
            params={},
            expected_output="Grafana login page",
            tip="Add Prometheus as a data source (URL: http://prometheus:9090) and import dashboard #1860 for Node Exporter.",
        ),
        QuickstartStep(
            title="Open Jaeger tracing",
            description="Jaeger shows distributed traces across services.",
            plugin="jaeger",
            tool="",
            params={},
            expected_output="Jaeger search UI",
            tip="Instrument your app with OpenTelemetry to send traces to Jaeger (endpoint: http://jaeger:4318).",
        ),
    ],
))


def get_quickstart(template_id: str) -> Quickstart | None:
    return QUICKSTARTS.get(template_id)


def list_quickstarts() -> list[dict[str, Any]]:
    return [
        {
            "template_id": qs.template_id,
            "title": qs.title,
            "description": qs.description,
            "estimated_minutes": qs.estimated_minutes,
            "total_steps": len(qs.steps),
        }
        for qs in QUICKSTARTS.values()
    ]
