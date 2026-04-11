"""Devcontainer Export — project a pysandbox sandbox as a VS Code devcontainer.

Generates a portable `.devcontainer/devcontainer.json` + `docker-compose.yml`
pair from the sandbox's installed plugin set, so a teammate can open the
repo in VS Code and get an identical stack without needing pysandbox itself.

The sandbox stays the source of truth; devcontainer is just a projection.
"""

from __future__ import annotations

from typing import Any


# Default host/container ports per plugin_id. Plugins that aren't listed
# fall back to no exposed ports (internal-only).
_DEFAULT_PORTS: dict[str, list[int]] = {
    "postgres": [5432],
    "mysql": [3306],
    "redis": [6379],
    "mongodb": [27017],
    "neo4j": [7474, 7687],
    "cassandra": [9042],
    "clickhouse": [8123, 9000],
    "elasticsearch": [9200],
    "dremio": [9047, 31010],
    "sqlite": [],
    "kafka": [9092],
    "rabbitmq": [5672, 15672],
    "nats": [4222, 8222],
    "minio": [9000, 9001],
    "localstack": [4566],
    "vault": [8200],
    "nessie": [19120],
    "prometheus": [9090],
    "grafana": [3000],
    "jaeger": [16686],
    "jupyter": [8888],
    "spark": [8080, 7077],
    "code-executor": [],
    "docker-daemon": [2375],
}

# Default image per plugin for devcontainer generation (image_template:version).
# We don't actually need to resolve the exact image used at runtime — the
# teammate just needs a stack that roughly matches. Anyone who needs prod
# parity should use `pysandbox export` → `pysandbox import`.
_DEFAULT_IMAGE: dict[str, str] = {
    "postgres": "postgres:{version}",
    "mysql": "mysql:{version}",
    "redis": "redis:{version}-alpine",
    "mongodb": "mongo:{version}",
    "neo4j": "neo4j:{version}",
    "cassandra": "cassandra:{version}",
    "clickhouse": "clickhouse/clickhouse-server:{version}",
    "elasticsearch": "docker.elastic.co/elasticsearch/elasticsearch:{version}",
    "dremio": "dremio/dremio-oss:{version}",
    "sqlite": "alpine/sqlite:{version}",
    "kafka": "confluentinc/confluent-local:{version}",
    "rabbitmq": "rabbitmq:{version}-management-alpine",
    "nats": "nats:{version}-alpine",
    "minio": "minio/minio:{version}",
    "localstack": "localstack/localstack:{version}",
    "vault": "hashicorp/vault:{version}",
    "nessie": "ghcr.io/projectnessie/nessie:{version}",
    "prometheus": "prom/prometheus:{version}",
    "grafana": "grafana/grafana:{version}",
    "jaeger": "jaegertracing/all-in-one:{version}",
    "jupyter": "jupyter/scipy-notebook:{version}",
    "spark": "apache/spark:{version}",
    "code-executor": "python:{version}-slim",
    "docker-daemon": "docker:{version}-dind",
}


def _resolve_image(plugin_id: str, version: str | None) -> str:
    """Compute the Docker image for a plugin with its version interpolated."""
    template = _DEFAULT_IMAGE.get(plugin_id, f"{plugin_id}:{{version}}")
    v = version or "latest"
    return template.replace("{version}", v)


class DevcontainerExporter:
    """Render a sandbox's plugin list as a VS Code devcontainer + compose file."""

    @staticmethod
    def render_compose(instances: list[dict[str, Any]]) -> dict[str, Any]:
        """Build a docker-compose.yml dict from installed plugin instances.

        Instances are the same shape returned by PluginInstanceRepo.list_instances.
        Plugins without a known default port still get a service entry, they
        just won't expose any ports to the host.
        """
        services: dict[str, Any] = {}
        # Start host ports at 20000 and increment for each exposed container port
        # so multiple plugins don't collide on the host.
        next_host_port = 20000

        # Sort by startup_order (and name) so service declaration order is stable
        # — YAML dict order is meaningful for human readers, not just Docker.
        ordered = sorted(
            instances,
            key=lambda i: (i.get("startup_order", 50), i.get("plugin_name", "")),
        )

        for inst in ordered:
            plugin_id = inst.get("plugin_id", "")
            plugin_name = inst.get("plugin_name", plugin_id)
            version = inst.get("version") or "latest"
            image = inst.get("image") or _resolve_image(plugin_id, version)

            svc: dict[str, Any] = {
                "image": image,
                "restart": "unless-stopped",
            }

            # Port mapping. If the runtime instance already has host_ports,
            # trust those; otherwise allocate fresh ones from our counter.
            host_ports = inst.get("host_ports") or {}
            if not host_ports:
                default_ports = _DEFAULT_PORTS.get(plugin_id, [])
                for cport in default_ports:
                    host_ports[str(cport)] = next_host_port
                    next_host_port += 1
            if host_ports:
                svc["ports"] = [f"{h}:{c}" for c, h in host_ports.items()]

            # Pass through any config the plugin declared (e.g. image override,
            # init args). We only forward keys docker-compose actually understands.
            cfg = inst.get("config") or {}
            if isinstance(cfg, dict):
                if "environment" in cfg:
                    svc["environment"] = cfg["environment"]
                if "command" in cfg:
                    svc["command"] = cfg["command"]

            services[plugin_name] = svc

        return {
            "version": "3.8",
            "services": services,
        }

    @staticmethod
    def render_devcontainer(
        sandbox: dict[str, Any],
        instances: list[dict[str, Any]],
        workspace_folder: str = "/workspace",
    ) -> dict[str, Any]:
        """Build a devcontainer.json for VS Code that references the compose file.

        Uses the "dockerComposeFile" form so VS Code knows how to bring the
        stack up. The `service` the VS Code window attaches to is a synthetic
        `workspace` container running python:3.11-slim — not one of the
        plugin containers — because attaching to (say) postgres would give
        you a broken shell.
        """
        sandbox_name = sandbox.get("name", "pysandbox")
        plugin_names = [
            i.get("plugin_name", i.get("plugin_id", "")) for i in instances
        ]
        # Useful env vars auto-injected from the plugins, so the workspace
        # container can talk to them by DNS name.
        forward_ports: list[int] = []
        for inst in instances:
            hp = inst.get("host_ports") or {}
            for h in hp.values():
                try:
                    forward_ports.append(int(h))
                except (TypeError, ValueError):
                    pass

        return {
            "name": f"pysandbox: {sandbox_name}",
            "dockerComposeFile": "docker-compose.yml",
            "service": "workspace",
            "workspaceFolder": workspace_folder,
            "forwardPorts": sorted(set(forward_ports)),
            "remoteUser": "root",
            "customizations": {
                "vscode": {
                    "extensions": [
                        "ms-python.python",
                        "ms-azuretools.vscode-docker",
                    ],
                },
            },
            # Metadata that's not part of the VS Code schema but is useful
            # for humans reading the file.
            "_pysandbox": {
                "source_sandbox_id": sandbox.get("id"),
                "source_sandbox_name": sandbox_name,
                "plugins": plugin_names,
            },
        }

    @staticmethod
    def render_workspace_service() -> dict[str, Any]:
        """The synthetic `workspace` service that VS Code attaches to.

        A minimal python:3.11-slim container with the repo bind-mounted.
        It stays alive via `sleep infinity` so VS Code has something to
        exec into.
        """
        return {
            "image": "python:3.11-slim",
            "command": ["sleep", "infinity"],
            "volumes": ["..:/workspace:cached"],
            "working_dir": "/workspace",
        }

    @staticmethod
    def export_bundle(
        sandbox: dict[str, Any],
        instances: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Render both files as a single bundle the API/CLI can hand back."""
        compose = DevcontainerExporter.render_compose(instances)
        # Prepend the workspace service so VS Code has something to attach to.
        compose["services"] = {
            "workspace": DevcontainerExporter.render_workspace_service(),
            **compose["services"],
        }
        devcontainer = DevcontainerExporter.render_devcontainer(sandbox, instances)
        return {
            "devcontainer.json": devcontainer,
            "docker-compose.yml": compose,
        }
