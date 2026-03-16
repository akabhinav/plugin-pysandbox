"""Shared test fixtures."""

import pytest

from pysandbox.agent.tool_registry import AgentToolRegistry
from pysandbox.db.repos.plugin_instance_repo import PluginInstanceRepo
from pysandbox.db.repos.sandbox_repo import SandboxRepo
from pysandbox.engine.event_bus import EventBus
from pysandbox.engine.resource_guard import ResourceGuard
from pysandbox.runtime.dns_server import SandboxDNSManager
from pysandbox.runtime.env_injector import EnvInjector
from pysandbox.runtime.port_allocator import PortAllocator
from pysandbox.runtime.secret_manager import SecretManager


@pytest.fixture
def event_bus():
    bus = EventBus()
    yield bus
    bus.clear()


@pytest.fixture
def tool_registry():
    return AgentToolRegistry()


@pytest.fixture
def secret_manager():
    key = SecretManager.generate_key()
    return SecretManager(key)


@pytest.fixture
def dns_manager():
    return SandboxDNSManager()


@pytest.fixture
def env_injector():
    return EnvInjector()


@pytest.fixture
def port_allocator():
    return PortAllocator(
        host_range_start=30000,
        host_range_end=30100,
        dns_range_start=6300,
        dns_range_end=6400,
    )


@pytest.fixture
def resource_guard():
    return ResourceGuard()


@pytest.fixture
def sandbox_repo():
    return SandboxRepo()


@pytest.fixture
def instance_repo():
    return PluginInstanceRepo()
