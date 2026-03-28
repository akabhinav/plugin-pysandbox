"""Comprehensive tests for ALL 21 plugins — every method on every plugin."""

import pytest

from pysandbox.plugin.loader import discover_and_load_all
from pysandbox.plugin.registry import get_plugin, is_registered, list_plugin_ids


@pytest.fixture(autouse=True, scope="module")
def _load():
    discover_and_load_all()


# --- Test data for every plugin ---
ALL_PLUGINS = [
    "postgres", "redis", "mysql", "mongodb", "elasticsearch",
    "clickhouse", "neo4j", "cassandra", "sqlite",
    "kafka", "rabbitmq", "nats",
    "localstack", "minio", "vault",
    "code-executor", "docker-daemon", "jupyter",
    "prometheus", "grafana", "jaeger",
]


class TestAllPluginsRegistered:
    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_plugin_is_registered(self, plugin_id):
        assert is_registered(plugin_id), f"{plugin_id} not registered"


class TestAllPluginsGenerateCredentials:
    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_generate_credentials(self, plugin_id):
        plugin = get_plugin(plugin_id)
        creds = plugin.generate_credentials({})
        assert isinstance(creds, dict)


class TestAllPluginsGetDockerConfig:
    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_get_docker_config(self, plugin_id):
        plugin = get_plugin(plugin_id)
        creds = plugin.generate_credentials({})
        cfg = plugin.get_docker_config(
            plugin_name="test-inst",
            sandbox_id="aaaabbbb-1234",
            dns_zone="aaaabbbb.sandbox.local",
            credentials=creds,
            config={},
            version=plugin.manifest.default_version,
        )
        assert isinstance(cfg, dict)
        assert "image" in cfg, f"{plugin_id}: docker config missing 'image'"


class TestAllPluginsGetEnvVars:
    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_get_env_vars(self, plugin_id):
        plugin = get_plugin(plugin_id)
        creds = plugin.generate_credentials({})
        env = plugin.get_env_vars("test-inst", "aaaabbbb.sandbox.local", creds, {})
        assert isinstance(env, dict)
        # All env vars must be string keys and values
        for k, v in env.items():
            assert isinstance(k, str), f"{plugin_id}: env key {k!r} not a string"
            assert isinstance(v, str), f"{plugin_id}: env val for {k} not a string"


class TestAllPluginsGetAgentTools:
    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_get_agent_tools(self, plugin_id):
        plugin = get_plugin(plugin_id)
        creds = plugin.generate_credentials({})
        tools = plugin.get_agent_tools("test-inst", "aaaabbbb.sandbox.local", creds, {})
        assert isinstance(tools, list)
        for tool in tools:
            assert tool.name, f"{plugin_id}: tool missing name"
            assert tool.description, f"{plugin_id}: tool {tool.name} missing description"
            assert callable(tool.handler), f"{plugin_id}: tool {tool.name} handler not callable"
            assert isinstance(tool.parameters, dict), f"{plugin_id}: tool {tool.name} params not dict"


class TestAllPluginsGetInitCommands:
    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_get_init_commands(self, plugin_id):
        plugin = get_plugin(plugin_id)
        creds = plugin.generate_credentials({})
        cmds = plugin.get_init_commands("test-inst", creds, {})
        assert isinstance(cmds, list)
        for cmd in cmds:
            assert isinstance(cmd, str)


class TestAllPluginsLifecycleHooks:
    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_on_install_doesnt_raise(self, plugin_id):
        """on_install hook can be called without error."""
        from pysandbox.plugin.base import PluginConnection
        plugin = get_plugin(plugin_id)
        conn = PluginConnection(
            plugin_id=plugin_id,
            dns_name="test.sandbox.local",
            internal_port=5432,
            host_port=None,
            env_vars={},
            credentials={},
            connection_strings={},
        )
        plugin.on_install(conn)  # Should not raise

    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_on_remove_doesnt_raise(self, plugin_id):
        from pysandbox.plugin.base import PluginConnection
        plugin = get_plugin(plugin_id)
        conn = PluginConnection(
            plugin_id=plugin_id,
            dns_name="test.sandbox.local",
            internal_port=5432,
            host_port=None,
            env_vars={},
            credentials={},
            connection_strings={},
        )
        plugin.on_remove(conn)  # Should not raise

    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_on_plugin_event_doesnt_raise(self, plugin_id):
        plugin = get_plugin(plugin_id)
        plugin.on_plugin_event("plugin.installed", "other-plugin", None)

    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_get_readiness_probe(self, plugin_id):
        plugin = get_plugin(plugin_id)
        probe = plugin.get_readiness_probe("test", "abc.sandbox.local")
        assert isinstance(probe, dict)

    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_get_volume_spec(self, plugin_id):
        plugin = get_plugin(plugin_id)
        spec = plugin.get_volume_spec("sandbox-123", "test")
        assert isinstance(spec, dict)


class TestAllPluginsManifest:
    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_manifest_id_matches(self, plugin_id):
        plugin = get_plugin(plugin_id)
        assert plugin.manifest.id == plugin_id

    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_manifest_has_health_check(self, plugin_id):
        plugin = get_plugin(plugin_id)
        hc = plugin.manifest.health_check
        assert hc.type in ("tcp", "http", "exec")
        assert hc.retries >= 1

    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_manifest_has_docker_image(self, plugin_id):
        plugin = get_plugin(plugin_id)
        assert plugin.manifest.docker_image

    @pytest.mark.parametrize("plugin_id", ALL_PLUGINS)
    def test_manifest_category_valid(self, plugin_id):
        plugin = get_plugin(plugin_id)
        assert plugin.manifest.category in (
            "databases", "messaging", "cloud", "runtime", "monitoring", "search"
        )


# --- Plugin-specific detailed tests ---


class TestMySQLDetails:
    def test_credentials_has_root_password(self):
        plugin = get_plugin("mysql")
        creds = plugin.generate_credentials({})
        assert "root_password" in creds
        assert "user" in creds
        assert "password" in creds

    def test_docker_config_sets_root_password(self):
        plugin = get_plugin("mysql")
        creds = plugin.generate_credentials({})
        cfg = plugin.get_docker_config("my-mysql", "sb1", "z", creds, {}, "8")
        assert cfg["environment"]["MYSQL_ROOT_PASSWORD"] == creds["root_password"]

    def test_env_vars_url_format(self):
        plugin = get_plugin("mysql")
        creds = {"user": "u", "password": "p", "root_password": "rp", "database": "db"}
        env = plugin.get_env_vars("my-mysql", "abc.sandbox.local", creds, {})
        assert env["MYSQL_URL"].startswith("mysql://")
        assert "u:p@" in env["MYSQL_URL"]

    def test_agent_tools(self):
        plugin = get_plugin("mysql")
        creds = {"user": "u", "password": "p", "root_password": "rp", "database": "db"}
        tools = plugin.get_agent_tools("x", "z.sandbox.local", creds, {})
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert "sql_query" in names
        assert "db_list_tables" in names


class TestMongoDBDetails:
    def test_credentials(self):
        plugin = get_plugin("mongodb")
        creds = plugin.generate_credentials({"db": "mydb"})
        assert creds["database"] == "mydb"

    def test_env_vars_include_uri(self):
        plugin = get_plugin("mongodb")
        creds = {"user": "u", "password": "p", "database": "d"}
        env = plugin.get_env_vars("mongo", "z.sandbox.local", creds, {})
        assert env["MONGODB_URI"].startswith("mongodb://")
        assert "authSource=admin" in env["MONGODB_URI"]

    def test_agent_tools_count(self):
        plugin = get_plugin("mongodb")
        creds = {"user": "u", "password": "p", "database": "d"}
        tools = plugin.get_agent_tools("mongo", "z.sandbox.local", creds, {})
        assert len(tools) == 8


class TestElasticsearchDetails:
    def test_docker_config_single_node(self):
        plugin = get_plugin("elasticsearch")
        creds = plugin.generate_credentials({})
        cfg = plugin.get_docker_config("es", "sb1", "z", creds, {}, "8.11.0")
        assert cfg["environment"]["discovery.type"] == "single-node"

    def test_env_vars(self):
        plugin = get_plugin("elasticsearch")
        creds = {"password": "p"}
        env = plugin.get_env_vars("es", "z.sandbox.local", creds, {})
        assert "ELASTICSEARCH_URL" in env
        assert env["ELASTICSEARCH_PORT"] == "9200"

    def test_agent_tools(self):
        plugin = get_plugin("elasticsearch")
        creds = {"password": "p"}
        tools = plugin.get_agent_tools("es", "z.sandbox.local", creds, {})
        assert len(tools) == 5
        names = {t.name for t in tools}
        assert "es_search" in names
        assert "es_cluster_health" in names


class TestClickHouseDetails:
    def test_env_vars(self):
        plugin = get_plugin("clickhouse")
        creds = {"user": "u", "password": "p", "database": "d"}
        env = plugin.get_env_vars("ch", "z.sandbox.local", creds, {})
        assert env["CLICKHOUSE_PORT"] == "8123"
        assert env["CLICKHOUSE_NATIVE_PORT"] == "9000"


class TestNeo4jDetails:
    def test_credentials(self):
        plugin = get_plugin("neo4j")
        creds = plugin.generate_credentials({})
        assert creds["user"] == "neo4j"

    def test_env_vars(self):
        plugin = get_plugin("neo4j")
        creds = {"user": "neo4j", "password": "p"}
        env = plugin.get_env_vars("neo4j", "z.sandbox.local", creds, {})
        assert env["NEO4J_URI"].startswith("bolt://")
        assert env["NEO4J_BOLT_PORT"] == "7687"

    def test_agent_tools(self):
        plugin = get_plugin("neo4j")
        creds = {"user": "neo4j", "password": "p"}
        tools = plugin.get_agent_tools("neo4j", "z.sandbox.local", creds, {})
        names = {t.name for t in tools}
        assert "cypher_query" in names


class TestCassandraDetails:
    def test_init_creates_keyspace(self):
        plugin = get_plugin("cassandra")
        creds = {"user": "c", "password": "p", "keyspace": "myks"}
        cmds = plugin.get_init_commands("c", creds, {})
        assert len(cmds) == 1
        assert "myks" in cmds[0]

    def test_env_vars(self):
        plugin = get_plugin("cassandra")
        creds = {"user": "c", "password": "p", "keyspace": "ks"}
        env = plugin.get_env_vars("c", "z.sandbox.local", creds, {})
        assert env["CASSANDRA_PORT"] == "9042"


class TestSQLiteDetails:
    def test_no_credentials(self):
        plugin = get_plugin("sqlite")
        creds = plugin.generate_credentials({})
        assert creds == {}

    def test_env_vars(self):
        plugin = get_plugin("sqlite")
        env = plugin.get_env_vars("sq", "z.sandbox.local", {}, {})
        assert env["DATABASE_URL"].startswith("sqlite:///")


class TestRabbitMQDetails:
    def test_credentials(self):
        plugin = get_plugin("rabbitmq")
        creds = plugin.generate_credentials({"vhost": "/test"})
        assert creds["vhost"] == "/test"

    def test_env_vars(self):
        plugin = get_plugin("rabbitmq")
        creds = {"user": "u", "password": "p", "vhost": "/"}
        env = plugin.get_env_vars("rmq", "z.sandbox.local", creds, {})
        assert env["RABBITMQ_URL"].startswith("amqp://")
        assert env["AMQP_URL"] == env["RABBITMQ_URL"]
        assert env["RABBITMQ_MANAGEMENT_PORT"] == "15672"

    def test_agent_tools(self):
        plugin = get_plugin("rabbitmq")
        creds = {"user": "u", "password": "p", "vhost": "/"}
        tools = plugin.get_agent_tools("rmq", "z.sandbox.local", creds, {})
        assert len(tools) == 5
        names = {t.name for t in tools}
        assert "rabbitmq_publish" in names
        assert "rabbitmq_consume" in names


class TestNATSDetails:
    def test_env_vars(self):
        plugin = get_plugin("nats")
        creds = {"user": "u", "password": "p"}
        env = plugin.get_env_vars("nats", "z.sandbox.local", creds, {})
        assert env["NATS_URL"].startswith("nats://")
        assert env["NATS_PORT"] == "4222"
        assert env["NATS_MONITOR_PORT"] == "8222"

    def test_docker_config_jetstream(self):
        plugin = get_plugin("nats")
        creds = {"user": "u", "password": "p"}
        cfg = plugin.get_docker_config("nats", "sb1", "z", creds, {}, "2.10")
        assert "--jetstream" in cfg["command"]

    def test_agent_tools(self):
        plugin = get_plugin("nats")
        creds = {"user": "u", "password": "p"}
        tools = plugin.get_agent_tools("nats", "z.sandbox.local", creds, {})
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert "nats_publish" in names


class TestMinIODetails:
    def test_credentials(self):
        plugin = get_plugin("minio")
        creds = plugin.generate_credentials({})
        assert "access_key" in creds
        assert "secret_key" in creds

    def test_env_vars(self):
        plugin = get_plugin("minio")
        creds = {"access_key": "ak", "secret_key": "sk"}
        env = plugin.get_env_vars("minio", "z.sandbox.local", creds, {})
        assert env["MINIO_ENDPOINT"].startswith("http://")
        assert env["AWS_ACCESS_KEY_ID"] == "ak"

    def test_agent_tools(self):
        plugin = get_plugin("minio")
        creds = {"access_key": "ak", "secret_key": "sk"}
        tools = plugin.get_agent_tools("minio", "z.sandbox.local", creds, {})
        assert len(tools) == 6
        tool_names = {t.name for t in tools}
        assert "s3_list_buckets" in tool_names

    def test_init_creates_buckets(self):
        plugin = get_plugin("minio")
        creds = {"access_key": "ak", "secret_key": "sk"}
        cmds = plugin.get_init_commands("minio", creds, {"buckets": ["data"]})
        assert len(cmds) == 1
        assert "data" in cmds[0]


class TestVaultDetails:
    def test_credentials(self):
        plugin = get_plugin("vault")
        creds = plugin.generate_credentials({})
        assert "root_token" in creds

    def test_env_vars(self):
        plugin = get_plugin("vault")
        creds = {"root_token": "t"}
        env = plugin.get_env_vars("vault", "z.sandbox.local", creds, {})
        assert env["VAULT_ADDR"].startswith("http://")
        assert env["VAULT_TOKEN"] == "t"

    def test_agent_tools(self):
        plugin = get_plugin("vault")
        creds = {"root_token": "t"}
        tools = plugin.get_agent_tools("vault", "z.sandbox.local", creds, {})
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert "vault_read" in names
        assert "vault_write" in names

    def test_init_enables_kv(self):
        plugin = get_plugin("vault")
        cmds = plugin.get_init_commands("vault", {"root_token": "t"}, {})
        assert len(cmds) == 1
        assert "kv-v2" in cmds[0]


class TestCodeExecutorDetails:
    def test_no_credentials(self):
        plugin = get_plugin("code-executor")
        assert plugin.generate_credentials({}) == {}

    def test_docker_config(self):
        plugin = get_plugin("code-executor")
        cfg = plugin.get_docker_config("exec", "sb1", "z", {}, {}, "3.12")
        assert "python" in cfg["image"]

    def test_env_vars(self):
        plugin = get_plugin("code-executor")
        env = plugin.get_env_vars("exec", "z.sandbox.local", {}, {})
        assert "CODE_EXECUTOR_HOST" in env

    def test_agent_tools(self):
        plugin = get_plugin("code-executor")
        tools = plugin.get_agent_tools("exec", "z.sandbox.local", {}, {})
        assert len(tools) == 4
        names = {t.name for t in tools}
        assert "shell_exec" in names
        assert "file_read" in names

    def test_init_installs_packages(self):
        plugin = get_plugin("code-executor")
        cmds = plugin.get_init_commands("exec", {}, {"pip_packages": ["requests", "numpy"]})
        assert len(cmds) == 2
        assert "pip install requests" in cmds[0]


class TestDockerDaemonDetails:
    def test_no_credentials(self):
        plugin = get_plugin("docker-daemon")
        assert plugin.generate_credentials({}) == {}

    def test_docker_config_dind(self):
        plugin = get_plugin("docker-daemon")
        cfg = plugin.get_docker_config("dind", "sb1", "z", {}, {}, "24")
        assert "dind" in cfg["image"]

    def test_env_vars(self):
        plugin = get_plugin("docker-daemon")
        env = plugin.get_env_vars("dind", "z.sandbox.local", {}, {})
        assert env["DOCKER_HOST"].startswith("tcp://")

    def test_agent_tools(self):
        plugin = get_plugin("docker-daemon")
        tools = plugin.get_agent_tools("dind", "z.sandbox.local", {}, {})
        assert len(tools) == 3
        names = {t.name for t in tools}
        assert "docker_run" in names
        assert "docker_build" in names
        assert "docker_ps" in names


class TestJupyterDetails:
    def test_credentials(self):
        plugin = get_plugin("jupyter")
        creds = plugin.generate_credentials({})
        assert "token" in creds

    def test_env_vars(self):
        plugin = get_plugin("jupyter")
        creds = {"token": "tok"}
        env = plugin.get_env_vars("jup", "z.sandbox.local", creds, {})
        assert env["JUPYTER_URL"].startswith("http://")
        assert env["JUPYTER_TOKEN"] == "tok"

    def test_agent_tools(self):
        plugin = get_plugin("jupyter")
        creds = {"token": "tok"}
        tools = plugin.get_agent_tools("jup", "z.sandbox.local", creds, {})
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "jupyter_execute" in names


class TestPrometheusDetails:
    def test_no_credentials(self):
        plugin = get_plugin("prometheus")
        assert plugin.generate_credentials({}) == {}

    def test_env_vars(self):
        plugin = get_plugin("prometheus")
        env = plugin.get_env_vars("prom", "z.sandbox.local", {}, {})
        assert env["PROMETHEUS_PORT"] == "9090"

    def test_agent_tools(self):
        plugin = get_plugin("prometheus")
        tools = plugin.get_agent_tools("prom", "z.sandbox.local", {}, {})
        assert len(tools) == 3
        names = {t.name for t in tools}
        assert "prometheus_query" in names


class TestGrafanaDetails:
    def test_credentials(self):
        plugin = get_plugin("grafana")
        creds = plugin.generate_credentials({})
        assert creds["user"] == "admin"
        assert len(creds["password"]) > 20

    def test_env_vars(self):
        plugin = get_plugin("grafana")
        creds = {"user": "admin", "password": "p"}
        env = plugin.get_env_vars("graf", "z.sandbox.local", creds, {})
        assert env["GRAFANA_PORT"] == "3000"

    def test_agent_tools(self):
        plugin = get_plugin("grafana")
        creds = {"user": "admin", "password": "p"}
        tools = plugin.get_agent_tools("graf", "z.sandbox.local", creds, {})
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "grafana_list_dashboards" in names


class TestJaegerDetails:
    def test_no_credentials(self):
        plugin = get_plugin("jaeger")
        assert plugin.generate_credentials({}) == {}

    def test_env_vars(self):
        plugin = get_plugin("jaeger")
        env = plugin.get_env_vars("jaeger", "z.sandbox.local", {}, {})
        assert env["JAEGER_QUERY_PORT"] == "16686"
        assert "OTEL_EXPORTER_OTLP_ENDPOINT" in env

    def test_agent_tools(self):
        plugin = get_plugin("jaeger")
        tools = plugin.get_agent_tools("jaeger", "z.sandbox.local", {}, {})
        assert len(tools) == 2
        names = {t.name for t in tools}
        assert "jaeger_traces" in names
        assert "jaeger_services" in names
