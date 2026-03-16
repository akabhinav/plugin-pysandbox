"""Tests for audit logging."""

from pysandbox.observability.audit_log import AuditLog


class TestAuditLog:
    def test_log_and_retrieve(self):
        audit = AuditLog()
        audit.log("sandbox.create", "sb1", actor="user1")
        entries = audit.get_entries()
        assert len(entries) == 1
        assert entries[0]["action"] == "sandbox.create"
        assert entries[0]["actor"] == "user1"
        assert entries[0]["sandbox_id"] == "sb1"

    def test_filter_by_sandbox(self):
        audit = AuditLog()
        audit.log("create", "sb1")
        audit.log("create", "sb2")
        audit.log("install", "sb1", plugin_id="postgres")

        sb1_entries = audit.get_entries("sb1")
        assert len(sb1_entries) == 2
        sb2_entries = audit.get_entries("sb2")
        assert len(sb2_entries) == 1

    def test_log_with_details(self):
        audit = AuditLog()
        audit.log("plugin.install", "sb1", plugin_id="redis", details={"version": "7"})
        entries = audit.get_entries()
        assert entries[0]["plugin_id"] == "redis"
        assert entries[0]["details"]["version"] == "7"

    def test_empty_entries(self):
        audit = AuditLog()
        assert audit.get_entries() == []
        assert audit.get_entries("sb1") == []

    def test_timestamp_present(self):
        audit = AuditLog()
        audit.log("test", "sb1")
        assert "timestamp" in audit.get_entries()[0]

    def test_default_actor_is_system(self):
        audit = AuditLog()
        audit.log("test", "sb1")
        assert audit.get_entries()[0]["actor"] == "system"
