"""Cost + Carbon Meter — attribute sandbox resource usage to dollars & CO₂.

This doesn't try to be a billing system. It's a *signal* surfaced during dev
so engineers notice when a sandbox is bloating the cloud bill — before it
shows up on an end-of-month invoice. The pricing table is deliberately
simple (per-vCPU-hour + per-GB-hour) and the defaults approximate AWS
on-demand pricing for us-east-1 in late 2024.

Users can override any rate via `CostMeter(rates={...})` so finance teams
can plug in their own contract pricing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class CostRates:
    """Rate table for computing dollar + CO₂ cost from raw resource usage."""

    # Dollars per vCPU-hour (AWS r6i on-demand us-east-1 ~ $0.063 / vCPU-hour)
    usd_per_vcpu_hour: float = 0.04
    # Dollars per GB-RAM-hour (~$0.005 / GB-hour implied by r6i)
    usd_per_gb_hour: float = 0.005
    # Dollars per GB-disk-month (gp3 EBS)
    usd_per_gb_disk_month: float = 0.08
    # CO₂ grams per kWh for electricity (US average grid ≈ 386 g/kWh in 2024)
    co2_g_per_kwh: float = 386.0
    # Power draw per active vCPU in watts (typical datacenter VM ≈ 7W/vCPU)
    watts_per_vcpu: float = 7.0
    # Power draw per GB of RAM in watts (~0.3W/GB typical DDR4/DDR5)
    watts_per_gb_ram: float = 0.3
    # PUE multiplier: data center overhead above the server draw itself.
    pue: float = 1.2


class CostMeter:
    """Compute cost + carbon for a sandbox from its current resource snapshot.

    Input shape matches what `/v1/monitoring/resources/{sid}` already returns.
    Output shape is designed to be UI-renderable: a headline total plus a
    per-plugin breakdown and an optional savings tip.
    """

    def __init__(self, rates: CostRates | None = None) -> None:
        self._rates = rates or CostRates()

    # ── public API ─────────────────────────────────────────────────────

    def estimate_sandbox(
        self,
        sandbox: dict[str, Any],
        instances: list[dict[str, Any]],
        stats: list[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Compute lifetime cost + CO₂ for a sandbox.

        Args:
            sandbox: dict with at least `created_at` (ISO string) and
                `id`. Resource limits (`total_cpu`, `total_memory_gb`,
                `total_disk_gb`) are used as a ceiling.
            instances: installed plugin instances; used for per-plugin
                attribution when stats are available.
            stats: optional live stats per container (cpu_percent,
                memory_usage_mb). If not provided we assume 100% of the
                sandbox quota is being used (pessimistic — flags idle
                sandboxes as expensive on purpose).
            now: injectable clock for deterministic tests.

        Returns:
            Dict with `age_hours`, `usd`, `co2_g`, `breakdown` (per plugin),
            and optionally `tip` (a savings suggestion string).
        """
        now = now or datetime.now(timezone.utc)
        age_hours = self._age_hours(sandbox.get("created_at"), now)

        total_cpu = float(sandbox.get("total_cpu", 0) or 0)
        total_mem_gb = float(sandbox.get("total_memory_gb", 0) or 0)
        total_disk_gb = float(sandbox.get("total_disk_gb", 0) or 0)

        # If we have live stats, derive actual utilization; otherwise assume
        # the sandbox is always using 100% of its quota (worst case — this
        # makes idle sandboxes look expensive so users notice them).
        utilization = self._utilization_from_stats(stats)
        effective_cpu = total_cpu * utilization["cpu_frac"]
        effective_mem_gb = total_mem_gb * utilization["mem_frac"]

        usd = self._compute_usd(effective_cpu, effective_mem_gb, total_disk_gb, age_hours)
        co2_g = self._compute_co2_grams(effective_cpu, effective_mem_gb, age_hours)

        breakdown = self._per_plugin_breakdown(instances, stats, age_hours)

        result: dict[str, Any] = {
            "sandbox_id": sandbox.get("id"),
            "age_hours": round(age_hours, 2),
            "usd": round(usd, 4),
            "co2_g": round(co2_g, 2),
            "co2_kg": round(co2_g / 1000.0, 4),
            "utilization": utilization,
            "breakdown": breakdown,
            "rates": {
                "usd_per_vcpu_hour": self._rates.usd_per_vcpu_hour,
                "usd_per_gb_hour": self._rates.usd_per_gb_hour,
                "co2_g_per_kwh": self._rates.co2_g_per_kwh,
            },
        }

        tip = self._suggest_savings(sandbox, utilization, age_hours, usd)
        if tip:
            result["tip"] = tip
        return result

    def estimate_fleet(
        self,
        sandboxes_with_stats: list[dict[str, Any]],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Compute totals across many sandboxes — for the `pysandbox cost` CLI.

        Each item in `sandboxes_with_stats` should be a dict with keys:
        `sandbox`, `instances`, `stats` (all optional except sandbox).
        """
        now = now or datetime.now(timezone.utc)
        rows = []
        total_usd = 0.0
        total_co2_g = 0.0
        for item in sandboxes_with_stats:
            row = self.estimate_sandbox(
                sandbox=item["sandbox"],
                instances=item.get("instances", []),
                stats=item.get("stats"),
                now=now,
            )
            rows.append({
                "sandbox_id": row["sandbox_id"],
                "sandbox_name": item["sandbox"].get("name"),
                "age_hours": row["age_hours"],
                "usd": row["usd"],
                "co2_g": row["co2_g"],
                "tip": row.get("tip"),
            })
            total_usd += row["usd"]
            total_co2_g += row["co2_g"]
        rows.sort(key=lambda r: r["usd"], reverse=True)
        return {
            "sandboxes": rows,
            "total_usd": round(total_usd, 4),
            "total_co2_g": round(total_co2_g, 2),
            "total_co2_kg": round(total_co2_g / 1000.0, 4),
            "count": len(rows),
        }

    # ── internals ──────────────────────────────────────────────────────

    def _age_hours(self, created_at_iso: str | None, now: datetime) -> float:
        if not created_at_iso:
            return 0.0
        try:
            created = datetime.fromisoformat(created_at_iso.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return max(0.0, (now - created).total_seconds() / 3600.0)

    def _utilization_from_stats(
        self, stats: list[dict[str, Any]] | None
    ) -> dict[str, float]:
        """Reduce raw per-container stats to mean cpu/mem utilization fractions."""
        if not stats:
            return {"cpu_frac": 1.0, "mem_frac": 1.0, "source": "assumed"}
        cpu_pcts = [s.get("cpu_percent", 0) or 0 for s in stats]
        mem_pcts = [s.get("memory_percent", 0) or 0 for s in stats]
        # Average utilization across the containers; this is imperfect but
        # fine as a cost signal — a precise number would require weighing
        # by container limits.
        cpu_frac = (sum(cpu_pcts) / len(cpu_pcts)) / 100.0 if cpu_pcts else 1.0
        mem_frac = (sum(mem_pcts) / len(mem_pcts)) / 100.0 if mem_pcts else 1.0
        # Clamp to [0.05, 1.0] — even a "0% CPU" container consumes base
        # resources, and reporting literal $0 hides the cost floor.
        cpu_frac = max(0.05, min(1.0, cpu_frac))
        mem_frac = max(0.05, min(1.0, mem_frac))
        return {"cpu_frac": cpu_frac, "mem_frac": mem_frac, "source": "stats"}

    def _compute_usd(
        self,
        effective_cpu: float,
        effective_mem_gb: float,
        total_disk_gb: float,
        age_hours: float,
    ) -> float:
        compute = effective_cpu * self._rates.usd_per_vcpu_hour * age_hours
        memory = effective_mem_gb * self._rates.usd_per_gb_hour * age_hours
        disk = (
            total_disk_gb
            * self._rates.usd_per_gb_disk_month
            * (age_hours / (24 * 30))  # monthly → hourly
        )
        return compute + memory + disk

    def _compute_co2_grams(
        self, effective_cpu: float, effective_mem_gb: float, age_hours: float
    ) -> float:
        watts = (
            effective_cpu * self._rates.watts_per_vcpu
            + effective_mem_gb * self._rates.watts_per_gb_ram
        ) * self._rates.pue
        kwh = (watts * age_hours) / 1000.0
        return kwh * self._rates.co2_g_per_kwh

    def _per_plugin_breakdown(
        self,
        instances: list[dict[str, Any]],
        stats: list[dict[str, Any]] | None,
        age_hours: float,
    ) -> list[dict[str, Any]]:
        """Attribute cost per plugin using its share of the total stat footprint."""
        if not instances:
            return []
        # Build a quick lookup from container_id -> stats entry so we can
        # match each plugin instance with its live usage.
        stat_by_cid: dict[str, dict[str, Any]] = {}
        for s in stats or []:
            cid = s.get("container_id", "")
            if cid:
                stat_by_cid[cid[:12]] = s

        rows = []
        for inst in instances:
            cid = (inst.get("container_id") or "")[:12]
            s = stat_by_cid.get(cid, {})
            cpu_frac = max(0.05, min(1.0, (s.get("cpu_percent", 0) or 0) / 100.0))
            mem_mb = s.get("memory_usage_mb", 0) or 0
            mem_gb = mem_mb / 1024.0 if mem_mb else 0.0
            # Fall back to a nominal 0.5 vCPU × 0.5 GB if we have no stats,
            # which maps to roughly the default plugin manifest limits.
            if not s:
                effective_cpu = 0.5
                effective_mem_gb = 0.5
            else:
                # Translate raw cpu_percent into an effective vCPU count. We
                # assume each container is limited to 2 vCPU by default; a
                # future improvement would read the manifest's `cpu` limit.
                effective_cpu = 2.0 * cpu_frac
                effective_mem_gb = mem_gb if mem_gb else 0.5
            usd = self._compute_usd(effective_cpu, effective_mem_gb, 0.0, age_hours)
            co2 = self._compute_co2_grams(effective_cpu, effective_mem_gb, age_hours)
            rows.append({
                "plugin_name": inst.get("plugin_name"),
                "plugin_id": inst.get("plugin_id"),
                "usd": round(usd, 4),
                "co2_g": round(co2, 2),
            })
        rows.sort(key=lambda r: r["usd"], reverse=True)
        return rows

    def _suggest_savings(
        self,
        sandbox: dict[str, Any],
        utilization: dict[str, float],
        age_hours: float,
        usd: float,
    ) -> str | None:
        """Emit a one-line tip when we see an obvious waste pattern."""
        if utilization.get("source") != "stats":
            # Without live stats we can't tell the user anything actionable.
            return None
        cpu_frac = utilization["cpu_frac"]
        if age_hours > 24 and cpu_frac < 0.1 and usd > 1.0:
            return (
                f"Sandbox has been running for {age_hours:.0f}h at "
                f"{cpu_frac*100:.0f}% CPU — consider pausing or destroying "
                f"to save ≈ ${usd:.2f}/day."
            )
        if age_hours > 72:
            return (
                f"Sandbox is {age_hours/24:.1f} days old. Dev sandboxes "
                "should typically have a TTL — see `pysandbox ttl set`."
            )
        return None
