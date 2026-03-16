"""Plugin manifest schema — validated from YAML before any plugin code runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResourceRequirements(BaseModel):
    cpu: str = "0.5"
    memory: str = "512m"
    disk_gb: float = 2.0


class PortSpec(BaseModel):
    port: int
    protocol: Literal["tcp", "udp"] = "tcp"
    name: str  # e.g. "http", "amqp", "cql"


class HealthCheckSpec(BaseModel):
    type: Literal["tcp", "http", "exec"] = "tcp"
    port: int | None = None
    path: str | None = None
    command: list[str] = Field(default_factory=list)
    interval_seconds: int = 5
    timeout_seconds: int = 3
    retries: int = 10


class ConfigParam(BaseModel):
    key: str
    type: Literal["string", "int", "bool", "list"] = "string"
    required: bool = False
    default: str | int | bool | list | None = None
    description: str = ""
    secret: bool = False


class PluginManifest(BaseModel):
    """Declarative description of a plugin — loaded from YAML."""

    # Identity
    id: str
    version: str
    display_name: str
    description: str
    category: Literal[
        "databases", "messaging", "cloud", "runtime", "monitoring", "search"
    ]
    tags: list[str] = Field(default_factory=list)
    icon: str = ""

    # Docker image
    docker_image: str
    supported_versions: list[str] = Field(default_factory=lambda: ["latest"])
    default_version: str = "latest"

    # Networking
    ports: list[PortSpec] = Field(default_factory=list)
    expose_by_default: bool = False

    # Resources
    resources: ResourceRequirements = Field(default_factory=ResourceRequirements)

    # Health
    health_check: HealthCheckSpec

    # Configuration schema
    config_params: list[ConfigParam] = Field(default_factory=list)

    # Ordering
    depends_on: list[str] = Field(default_factory=list)
    startup_order: int = 50

    # Capability flags
    generates_credentials: bool = True
    persistent_data: bool = True
    supports_hot_reload: bool = False
