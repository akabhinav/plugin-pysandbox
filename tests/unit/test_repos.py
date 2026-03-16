"""Tests for in-memory repositories."""

import pytest

from pysandbox.db.repos.plugin_instance_repo import PluginInstanceRepo
from pysandbox.db.repos.sandbox_repo import SandboxRepo


class TestSandboxRepo:
    @pytest.mark.asyncio
    async def test_create_and_get(self, sandbox_repo):
        sandbox = {"id": "sb1", "name": "test", "status": "running"}
        await sandbox_repo.create(sandbox)
        result = await sandbox_repo.get("sb1")
        assert result["name"] == "test"

    @pytest.mark.asyncio
    async def test_update(self, sandbox_repo):
        sandbox = {"id": "sb1", "name": "test", "status": "creating"}
        await sandbox_repo.create(sandbox)
        sandbox["status"] = "running"
        await sandbox_repo.update(sandbox)
        result = await sandbox_repo.get("sb1")
        assert result["status"] == "running"

    @pytest.mark.asyncio
    async def test_list_all(self, sandbox_repo):
        await sandbox_repo.create({"id": "sb1", "name": "a", "status": "running"})
        await sandbox_repo.create({"id": "sb2", "name": "b", "status": "running"})
        result = await sandbox_repo.list_all()
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, sandbox_repo):
        result = await sandbox_repo.get("nonexistent")
        assert result is None


class TestPluginInstanceRepo:
    @pytest.mark.asyncio
    async def test_create_and_get(self, instance_repo):
        await instance_repo.create_instance(
            sandbox_id="sb1",
            plugin_id="postgres",
            plugin_name="my-pg",
            version="16",
            config={},
            credentials_encrypted="enc",
            container_id="cid",
            container_ip="172.20.0.3",
            internal_port=5432,
            host_port=None,
            env_var_keys=["POSTGRES_URL"],
            agent_tool_names=["sql_query"],
        )
        result = await instance_repo.get_instance("sb1", "my-pg")
        assert result is not None
        assert result["plugin_id"] == "postgres"

    @pytest.mark.asyncio
    async def test_list_instances(self, instance_repo):
        await instance_repo.create_instance("sb1", "postgres", "pg", "16", {}, "", "c1", "1.2.3.4", 5432, None, [], [])
        await instance_repo.create_instance("sb1", "redis", "redis", "7", {}, "", "c2", "1.2.3.5", 6379, None, [], [])
        result = await instance_repo.list_instances("sb1")
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_mark_removed(self, instance_repo):
        await instance_repo.create_instance("sb1", "redis", "redis", "7", {}, "", "c1", "1.2.3.4", 6379, None, [], [])
        await instance_repo.mark_removed("sb1", "redis")
        result = await instance_repo.list_instances("sb1")
        assert len(result) == 0  # Removed instances are filtered

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, instance_repo):
        result = await instance_repo.get_instance("sb1", "nope")
        assert result is None
