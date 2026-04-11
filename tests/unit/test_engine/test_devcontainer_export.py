"""Tests for DevcontainerExporter."""

from pysandbox.engine.devcontainer_export import DevcontainerExporter


def test_render_compose_emits_service_per_plugin():
    instances = [
        {"plugin_id": "postgres", "plugin_name": "db", "version": "16"},
        {"plugin_id": "redis", "plugin_name": "cache", "version": "7"},
    ]
    compose = DevcontainerExporter.render_compose(instances)

    assert compose["version"] == "3.8"
    assert "db" in compose["services"]
    assert "cache" in compose["services"]
    assert compose["services"]["db"]["image"] == "postgres:16"
    assert compose["services"]["cache"]["image"] == "redis:7-alpine"


def test_render_compose_allocates_host_ports_when_missing():
    instances = [
        {"plugin_id": "postgres", "plugin_name": "db", "version": "16"},
        {"plugin_id": "redis", "plugin_name": "cache", "version": "7"},
    ]
    compose = DevcontainerExporter.render_compose(instances)

    # Each plugin gets at least one port mapping from our defaults table.
    assert "ports" in compose["services"]["db"]
    assert "ports" in compose["services"]["cache"]
    # Host ports must not collide.
    host_ports = set()
    for svc in compose["services"].values():
        for mapping in svc.get("ports", []):
            host_ports.add(mapping.split(":")[0])
    assert len(host_ports) == 2


def test_render_compose_honors_existing_host_ports():
    instances = [
        {
            "plugin_id": "postgres",
            "plugin_name": "db",
            "version": "16",
            "host_ports": {"5432": 24242},
        },
    ]
    compose = DevcontainerExporter.render_compose(instances)
    assert compose["services"]["db"]["ports"] == ["24242:5432"]


def test_render_compose_respects_startup_order():
    instances = [
        {"plugin_id": "redis", "plugin_name": "cache", "version": "7", "startup_order": 90},
        {"plugin_id": "postgres", "plugin_name": "db", "version": "16", "startup_order": 10},
    ]
    compose = DevcontainerExporter.render_compose(instances)
    # db (order=10) should come before cache (order=90).
    keys = list(compose["services"].keys())
    assert keys.index("db") < keys.index("cache")


def test_render_devcontainer_includes_forward_ports():
    sandbox = {"id": "sb-1", "name": "my-stack"}
    instances = [
        {
            "plugin_id": "postgres",
            "plugin_name": "db",
            "version": "16",
            "host_ports": {"5432": 20000},
        },
    ]
    dc = DevcontainerExporter.render_devcontainer(sandbox, instances)

    assert dc["name"] == "pysandbox: my-stack"
    assert dc["dockerComposeFile"] == "docker-compose.yml"
    assert dc["service"] == "workspace"
    assert 20000 in dc["forwardPorts"]
    assert dc["_pysandbox"]["source_sandbox_id"] == "sb-1"
    assert dc["_pysandbox"]["plugins"] == ["db"]


def test_export_bundle_prepends_workspace_service():
    sandbox = {"id": "sb-1", "name": "my-stack"}
    instances = [
        {"plugin_id": "redis", "plugin_name": "cache", "version": "7"},
    ]
    bundle = DevcontainerExporter.export_bundle(sandbox, instances)

    assert "devcontainer.json" in bundle
    assert "docker-compose.yml" in bundle

    services = bundle["docker-compose.yml"]["services"]
    # workspace must be first so VS Code has something to attach to before
    # the real plugins come up.
    assert list(services.keys())[0] == "workspace"
    assert services["workspace"]["image"] == "python:3.11-slim"
    assert services["workspace"]["command"] == ["sleep", "infinity"]


def test_unknown_plugin_falls_back_to_generic_image():
    instances = [
        {"plugin_id": "mystery", "plugin_name": "m", "version": "2.0"},
    ]
    compose = DevcontainerExporter.render_compose(instances)
    assert compose["services"]["m"]["image"] == "mystery:2.0"
