"""ORM models for sandbox and plugin state."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class SandboxModel(Base):
    __tablename__ = "sandboxes"

    id = Column(String(36), primary_key=True)
    name = Column(String(100), nullable=False)
    owner_id = Column(String(100), nullable=False, default="default")
    org_id = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="creating")
    docker_network = Column(String(100), nullable=True)
    dns_zone = Column(String(100), nullable=True)
    dns_port = Column(Integer, nullable=True)
    spec = Column(JSON, nullable=True)
    total_cpu = Column(Float, default=4.0)
    total_memory_gb = Column(Float, default=8.0)
    total_disk_gb = Column(Float, default=50.0)
    error = Column(Text, nullable=True)
    tags = Column(JSON, default=dict)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PluginInstanceModel(Base):
    __tablename__ = "plugin_instances"

    id = Column(String(36), primary_key=True)
    sandbox_id = Column(String(36), nullable=False, index=True)
    plugin_id = Column(String(50), nullable=False)
    plugin_name = Column(String(50), nullable=False)
    version = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="installing")
    container_id = Column(String(100), nullable=True)
    container_ip = Column(String(20), nullable=True)
    internal_port = Column(Integer, nullable=True)
    host_port = Column(Integer, nullable=True)
    config = Column(JSON, default=dict)
    credentials_encrypted = Column(Text, nullable=True)
    env_var_keys = Column(JSON, default=list)
    agent_tool_names = Column(JSON, default=list)
    startup_order = Column(Integer, default=50)
    installed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    removed_at = Column(DateTime, nullable=True)
