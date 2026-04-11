"""Tests for CostMeter."""

from datetime import datetime, timedelta, timezone

from pysandbox.engine.cost_meter import CostMeter, CostRates


def _now() -> datetime:
    return datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_zero_age_yields_zero_cost():
    meter = CostMeter()
    sb = {"id": "sb-1", "created_at": _now().isoformat(), "total_cpu": 4, "total_memory_gb": 8}
    out = meter.estimate_sandbox(sb, instances=[], now=_now())
    assert out["usd"] == 0.0
    assert out["co2_g"] == 0.0
    assert out["age_hours"] == 0.0


def test_cost_scales_with_age_and_quota():
    meter = CostMeter(CostRates(usd_per_vcpu_hour=0.1, usd_per_gb_hour=0.01))
    now = _now()
    sb = {
        "id": "sb-1",
        "created_at": (now - timedelta(hours=2)).isoformat(),
        "total_cpu": 4,
        "total_memory_gb": 8,
        "total_disk_gb": 0,
    }
    out = meter.estimate_sandbox(sb, instances=[], now=now)
    # No live stats → assumed 100% utilization.
    # compute = 4 vCPU * $0.10 * 2h = $0.80
    # memory  = 8 GB  * $0.01 * 2h = $0.16
    # total   = $0.96
    assert abs(out["usd"] - 0.96) < 1e-6
    assert out["age_hours"] == 2.0


def test_utilization_pulled_from_live_stats():
    meter = CostMeter(CostRates(usd_per_vcpu_hour=0.1, usd_per_gb_hour=0.0))
    now = _now()
    sb = {
        "id": "sb-1",
        "created_at": (now - timedelta(hours=10)).isoformat(),
        "total_cpu": 10,
        "total_memory_gb": 0,
    }
    # 20% average CPU, floor at 5% gives 20%.
    stats = [
        {"cpu_percent": 20, "memory_percent": 0, "container_id": "a" * 12},
    ]
    out = meter.estimate_sandbox(sb, instances=[], stats=stats, now=now)
    # effective_cpu = 10 * 0.20 = 2 vCPU → 2 * 0.10 * 10h = $2.00
    assert abs(out["usd"] - 2.0) < 1e-6
    assert out["utilization"]["source"] == "stats"
    assert out["utilization"]["cpu_frac"] == 0.2


def test_utilization_is_floored_so_idle_is_not_free():
    meter = CostMeter()
    now = _now()
    sb = {
        "id": "sb-1",
        "created_at": (now - timedelta(hours=1)).isoformat(),
        "total_cpu": 4,
        "total_memory_gb": 8,
    }
    stats = [{"cpu_percent": 0, "memory_percent": 0, "container_id": "a"}]
    out = meter.estimate_sandbox(sb, instances=[], stats=stats, now=now)
    # Cost should be > 0 thanks to the 5% floor.
    assert out["usd"] > 0


def test_idle_multi_day_triggers_savings_tip():
    meter = CostMeter(CostRates(usd_per_vcpu_hour=0.1, usd_per_gb_hour=0.01))
    now = _now()
    sb = {
        "id": "sb-1",
        "created_at": (now - timedelta(hours=48)).isoformat(),
        "total_cpu": 8,
        "total_memory_gb": 16,
    }
    stats = [{"cpu_percent": 2, "memory_percent": 50, "container_id": "a"}]
    out = meter.estimate_sandbox(sb, instances=[], stats=stats, now=now)
    assert out["tip"] is not None
    assert "pausing" in out["tip"] or "destroying" in out["tip"]


def test_very_old_sandbox_triggers_ttl_tip():
    meter = CostMeter()
    now = _now()
    sb = {
        "id": "sb-1",
        "created_at": (now - timedelta(hours=100)).isoformat(),
        "total_cpu": 4,
        "total_memory_gb": 8,
    }
    stats = [{"cpu_percent": 80, "memory_percent": 70, "container_id": "a"}]
    out = meter.estimate_sandbox(sb, instances=[], stats=stats, now=now)
    assert "TTL" in (out.get("tip") or "") or "days old" in (out.get("tip") or "")


def test_fleet_aggregate_sums_and_sorts():
    meter = CostMeter(CostRates(usd_per_vcpu_hour=0.1, usd_per_gb_hour=0.0))
    now = _now()
    items = [
        {
            "sandbox": {
                "id": "cheap",
                "name": "cheap",
                "created_at": (now - timedelta(hours=1)).isoformat(),
                "total_cpu": 1,
                "total_memory_gb": 0,
            },
            "instances": [],
            "stats": None,
        },
        {
            "sandbox": {
                "id": "expensive",
                "name": "expensive",
                "created_at": (now - timedelta(hours=10)).isoformat(),
                "total_cpu": 8,
                "total_memory_gb": 0,
            },
            "instances": [],
            "stats": None,
        },
    ]
    out = meter.estimate_fleet(items, now=now)
    # expensive first (sorted desc)
    assert out["sandboxes"][0]["sandbox_id"] == "expensive"
    assert out["count"] == 2
    assert out["total_usd"] > 0


def test_per_plugin_breakdown_uses_stats_when_available():
    meter = CostMeter(CostRates(usd_per_vcpu_hour=1.0, usd_per_gb_hour=0.0))
    now = _now()
    sb = {
        "id": "sb-1",
        "created_at": (now - timedelta(hours=1)).isoformat(),
        "total_cpu": 4,
        "total_memory_gb": 0,
    }
    cid = "a" * 64
    instances = [
        {"plugin_id": "postgres", "plugin_name": "db", "container_id": cid},
    ]
    stats = [{"cpu_percent": 50, "memory_percent": 50, "container_id": cid}]
    out = meter.estimate_sandbox(sb, instances, stats, now=now)
    assert len(out["breakdown"]) == 1
    assert out["breakdown"][0]["plugin_name"] == "db"
    assert out["breakdown"][0]["usd"] > 0


def test_co2_tracks_cpu_and_memory():
    meter = CostMeter()
    now = _now()
    sb_low = {
        "id": "low",
        "created_at": (now - timedelta(hours=1)).isoformat(),
        "total_cpu": 1,
        "total_memory_gb": 1,
    }
    sb_high = {
        "id": "high",
        "created_at": (now - timedelta(hours=1)).isoformat(),
        "total_cpu": 16,
        "total_memory_gb": 32,
    }
    low = meter.estimate_sandbox(sb_low, [], now=now)
    high = meter.estimate_sandbox(sb_high, [], now=now)
    assert high["co2_g"] > low["co2_g"] * 10
