"""Tests for Sandbox TTL feature."""

import pytest
from datetime import datetime, timezone

from pysandbox.engine.sandbox_ttl import SandboxTTLManager


class TestSandboxTTL:
    def test_set_ttl(self):
        mgr = SandboxTTLManager()
        info = mgr.set_ttl("sb1", 3600)
        assert info["sandbox_id"] == "sb1"
        assert info["ttl_seconds"] == 3600
        assert info["created_at"]
        assert info["expires_at"]

    def test_get_ttl(self):
        mgr = SandboxTTLManager()
        mgr.set_ttl("sb1", 3600)
        info = mgr.get_ttl("sb1")
        assert info is not None
        assert info["remaining_seconds"] > 0
        assert info["remaining_seconds"] <= 3600

    def test_get_ttl_nonexistent(self):
        mgr = SandboxTTLManager()
        assert mgr.get_ttl("sb999") is None

    def test_remove_ttl(self):
        mgr = SandboxTTLManager()
        mgr.set_ttl("sb1", 3600)
        assert mgr.remove_ttl("sb1") is True
        assert mgr.get_ttl("sb1") is None

    def test_remove_ttl_nonexistent(self):
        mgr = SandboxTTLManager()
        assert mgr.remove_ttl("sb999") is False

    def test_list_ttls(self):
        mgr = SandboxTTLManager()
        mgr.set_ttl("sb1", 3600)
        mgr.set_ttl("sb2", 7200)
        ttls = mgr.list_ttls()
        assert len(ttls) == 2
        sids = {t["sandbox_id"] for t in ttls}
        assert "sb1" in sids
        assert "sb2" in sids

    def test_get_expired_none(self):
        mgr = SandboxTTLManager()
        mgr.set_ttl("sb1", 3600)
        expired = mgr.get_expired()
        assert len(expired) == 0

    def test_get_expired_with_past(self):
        mgr = SandboxTTLManager()
        # Manually set an expired entry
        past = datetime(2020, 1, 1, tzinfo=timezone.utc)
        mgr._ttls["sb1"] = {
            "sandbox_id": "sb1",
            "ttl_seconds": 60,
            "created_at": past.isoformat(),
            "expires_at": past.isoformat(),
        }
        expired = mgr.get_expired()
        assert "sb1" in expired

    def test_update_ttl(self):
        mgr = SandboxTTLManager()
        mgr.set_ttl("sb1", 3600)
        mgr.set_ttl("sb1", 7200)
        info = mgr.get_ttl("sb1")
        assert info["ttl_seconds"] == 7200
