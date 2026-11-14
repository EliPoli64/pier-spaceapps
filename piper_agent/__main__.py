"""CLI entry point: python -m piper_agent --lat FLOAT --lon FLOAT --date YYYY-MM-DD [--demo] [--demo-name X]"""
from __future__ import annotations

import argparse
import sys

from piper_agent.agent import plan_text_only


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PIER — Extreme-weather Recovery Planner (Spec 3)"
    )
    parser.add_argument("--lat", type=float, required=True, help="Field latitude")
    parser.add_argument("--lon", type=float, required=True, help="Field longitude")
    parser.add_argument(
        "--date", type=str, required=True, help="Current date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=True,
        help="Use cached demo data (default: True)",
    )
    parser.add_argument(
        "--no-demo",
        action="store_true",
        default=False,
        help="Attempt live NASA path (production; not implemented)",
    )
    parser.add_argument(
        "--demo-name",
        type=str,
        choices=["flood", "drought", "normal"],
        default=None,
        help="Select a specific demo scenario",
    )
    args = parser.parse_args(argv)

    demo_mode = args.demo and not args.no_demo

    try:
        text = plan_text_only(
            lat=args.lat,
            lon=args.lon,
            current_date=args.date,
            demo_mode=demo_mode,
            demo_name=args.demo_name,
        )
    except NotImplementedError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
