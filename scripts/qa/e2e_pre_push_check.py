"""End-to-end pre-push verification for the GDD merge CI fix.

Runs offline demos, API smoke, agent contract checks, and an optional live
NASA POWER attempt (credentials from .env). Writes a JSON report under docs/.

Usage:
  python scripts/qa/e2e_pre_push_check.py
  python scripts/qa/e2e_pre_push_check.py --skip-live
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.chdir(ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:  # noqa: BLE001
    pass


def _ok(name: str, detail: Any = None) -> dict[str, Any]:
    return {"name": name, "status": "pass", "detail": detail}


def _fail(name: str, detail: Any) -> dict[str, Any]:
    return {"name": name, "status": "fail", "detail": detail}


def _skip(name: str, detail: Any) -> dict[str, Any]:
    return {"name": name, "status": "skip", "detail": detail}


def check_demo(scenario: str, lat: float, lon: float, date: str) -> dict[str, Any]:
    from piper_agent.agent import run_pier

    res = run_pier(lat, lon, date, demo_mode=True, demo_name=scenario)
    er = res["event_result"]
    crops = res.get("crops") or []
    expected = {
        "flood": "flood",
        "drought": "drought",
        "normal": "none",
        "late_flood": "flood",
    }[scenario]
    if er.event_type != expected:
        return _fail(
            f"demo:{scenario}",
            f"expected event_type={expected}, got {er.event_type}",
        )
    if scenario in ("flood", "drought") and len(crops) < 1:
        return _fail(f"demo:{scenario}", "expected >=1 rescue crop")
    if scenario == "late_flood" and not res["recovery_plan"].fallback:
        return _fail(f"demo:{scenario}", "expected fallback cover crop")
    return _ok(
        f"demo:{scenario}",
        {
            "event_type": er.event_type,
            "confidence": er.confidence,
            "n_crops": len(crops),
            "fuente_datos": res.get("fuente_datos"),
            "remaining_method": (res["gdd_result"].details or {}).get(
                "remaining_method"
            ),
            "top_crop": crops[0].crop if crops else None,
        },
    )


def check_season_start_override() -> dict[str, Any]:
    from piper_agent.agent import run_pier

    base = run_pier(41.8, -93.6, "2025-05-15", True, "flood")
    custom = run_pier(
        41.8, -93.6, "2025-05-15", True, "flood", season_start="2025-04-15"
    )
    base_ss = (base["gdd_result"].details or {}).get("season_start")
    custom_ss = (custom["gdd_result"].details or {}).get("season_start")
    if custom_ss != "2025-04-15":
        return _fail("season_start_override", f"got {custom_ss}")
    if custom["gdd_result"].gdd_accumulated >= base["gdd_result"].gdd_accumulated:
        return _fail(
            "season_start_override",
            "custom season_start should accumulate less GDD",
        )
    return _ok(
        "season_start_override",
        {"base_season_start": base_ss, "custom_season_start": custom_ss},
    )


def check_api() -> dict[str, Any]:
    from fastapi.testclient import TestClient

    from piper_agent.api import security
    from piper_agent.api.main import app

    # .env may set PIER_DEMO_MODE=0 (production), which requires an API key.
    # For local smoke we force anonymous demo access without mutating secrets.
    prev_require = os.environ.get("PIER_REQUIRE_API_KEY")
    prev_key = os.environ.get("PIER_API_KEY")
    os.environ["PIER_REQUIRE_API_KEY"] = "0"
    os.environ.pop("PIER_API_KEY", None)
    security.reset_rate_limits()
    try:
        client = TestClient(app)
        health = client.get("/health")
        if health.status_code != 200:
            return _fail("api:health", health.text)
        body = {
            "lat": 41.8,
            "lon": -93.6,
            "current_date": "2025-05-15",
            "demo_mode": True,
            "demo_name": "flood",
        }
        plan = client.post("/generate_plan", json=body)
        if plan.status_code != 200:
            return _fail("api:generate_plan", f"{plan.status_code} {plan.text[:400]}")
        payload = plan.json()
        if payload.get("event_type") != "flood":
            return _fail(
                "api:generate_plan",
                f"expected event_type=flood, got {payload.get('event_type')}",
            )
        return _ok(
            "api:generate_plan",
            {
                "health": health.json().get("status"),
                "event_type": payload.get("event_type"),
                "fuente_datos": payload.get("fuente_datos"),
                "n_crops": len(payload.get("crops") or []),
                "keys": sorted(payload.keys())[:20],
            },
        )
    finally:
        if prev_require is None:
            os.environ.pop("PIER_REQUIRE_API_KEY", None)
        else:
            os.environ["PIER_REQUIRE_API_KEY"] = prev_require
        if prev_key is None:
            os.environ.pop("PIER_API_KEY", None)
        else:
            os.environ["PIER_API_KEY"] = prev_key
        security.reset_rate_limits()


def check_live(skip: bool) -> dict[str, Any]:
    if skip:
        return _skip("live:nasa_power", "skipped by flag")
    user = os.getenv("EARTHDATA_USERNAME", "").strip()
    password = os.getenv("EARTHDATA_PASSWORD", "").strip()
    if not user or not password or user.startswith("your_"):
        return _skip("live:nasa_power", "EARTHDATA credentials missing/placeholder")

    from piper_agent.agent import run_pier

    try:
        res = run_pier(
            41.8,
            -93.6,
            "2025-06-25",
            demo_mode=False,
            season_start="2025-04-01",
        )
    except Exception as exc:  # noqa: BLE001
        return _fail("live:nasa_power", f"{type(exc).__name__}: {exc}")

    fuente = res.get("fuente_datos")
    fallback = res.get("fallback_reason")
    gdd = res["gdd_result"]
    detail = {
        "fuente_datos": fuente,
        "fallback_reason": fallback,
        "event_type": res["event_result"].event_type,
        "gdd_accumulated": gdd.gdd_accumulated,
        "gdd_remaining": gdd.gdd_remaining,
        "remaining_method": (gdd.details or {}).get("remaining_method"),
        "data_status": (gdd.details or {}).get("data_status"),
        "n_crops": len(res.get("crops") or []),
        "has_plan_text": bool(res.get("plan_text")),
    }
    # Live path may fall back to synthetic if NASA is unreachable; that is OK
    # as long as it is labeled and the pipeline completes.
    if not res.get("plan_text"):
        return _fail("live:nasa_power", detail)
    if fuente not in ("nasa_power", "nasa_power+imerg", "sintetico"):
        return _fail("live:nasa_power", detail)
    return _ok("live:nasa_power", detail)


def check_cli_json() -> dict[str, Any]:
    import io
    from contextlib import redirect_stdout

    from piper_agent import __main__ as cli

    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cli.main([
            "--lat",
            "41.8",
            "--lon",
            "-93.6",
            "--date",
            "2025-05-15",
            "--demo-name",
            "flood",
            "--json",
        ])
    if rc != 0:
        return _fail("cli:flood_json", f"exit={rc}")
    payload = json.loads(buf.getvalue())
    if payload.get("demo_name") != "flood":
        return _fail("cli:flood_json", f"unexpected payload demo_name={payload.get('demo_name')}")
    return _ok(
        "cli:flood_json",
        {
            "exit": rc,
            "event_type": (payload.get("event_result") or {}).get("event_type"),
            "remaining_method": (
                (payload.get("gdd_result") or {}).get("details") or {}
            ).get("remaining_method"),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live", action="store_true")
    parser.add_argument(
        "--out",
        default=str(ROOT / "docs" / "E2E_PRE_PUSH_REPORT.json"),
    )
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    scenarios = [
        ("flood", 41.8, -93.6, "2025-05-15"),
        ("drought", 9.0, 41.0, "2025-01-30"),
        ("normal", 41.8, -93.6, "2025-07-07"),
        ("late_flood", 41.8, -93.6, "2025-08-28"),
    ]
    for sc, lat, lon, dt in scenarios:
        try:
            checks.append(check_demo(sc, lat, lon, dt))
        except Exception as exc:  # noqa: BLE001
            checks.append(_fail(f"demo:{sc}", f"{type(exc).__name__}: {exc}"))

    for fn in (
        check_season_start_override,
        check_cli_json,
        check_api,
    ):
        try:
            checks.append(fn())
        except Exception as exc:  # noqa: BLE001
            checks.append(
                _fail(fn.__name__, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}")
            )

    try:
        checks.append(check_live(args.skip_live))
    except Exception as exc:  # noqa: BLE001
        checks.append(_fail("live:nasa_power", f"{type(exc).__name__}: {exc}"))

    summary = {
        "pass": sum(1 for c in checks if c["status"] == "pass"),
        "fail": sum(1 for c in checks if c["status"] == "fail"),
        "skip": sum(1 for c in checks if c["status"] == "skip"),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "repo": str(ROOT),
        "branch_hint": "master (local CI fix)",
        "summary": summary,
        "checks": checks,
        "credentials_present": {
            "EARTHDATA_USERNAME": bool(os.getenv("EARTHDATA_USERNAME")),
            "EARTHDATA_PASSWORD": bool(os.getenv("EARTHDATA_PASSWORD")),
            "PIER_OPENET_API_KEY": bool(os.getenv("PIER_OPENET_API_KEY")),
            "PIER_SMAP_API_KEY": bool(os.getenv("PIER_SMAP_API_KEY")),
        },
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print(json.dumps({"summary": summary, "report": str(out)}, indent=2))
    for c in checks:
        mark = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[c["status"]]
        print(f"[{mark}] {c['name']}")
    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
