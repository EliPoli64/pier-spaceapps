#!/usr/bin/env python
"""Demo SMS simulator for Elias's branch (feat/docs-entrega).

Run from repo root:
    python piper_agent/ui/sms_simulator.py --lat 41.8 --lon -93.6 --date 2025-06-20 --demo-name flood

This calls run_pier and formats the output as a concise SMS reply (≤160 chars),
mimicking what the SMS gateway (Matias's branch) would send to a farmer.
"""

import argparse
import sys
from piper_agent.agent import run_pier


def sms_format(result: dict) -> str:
    """Format the agent result into a concise SMS reply ≤160 chars."""
    event_type = result.get("event_result", {}).get("event_type", "none")
    crops = result.get("crops", [])

    if event_type == "none":
        return ("No extreme event detected. Normal planting plan stands. "
                "-- PIER demo mode")

    if not crops:
        return ("The season's cash crop is lost; this recommendation "
                "is soil protection only. Plant cereal rye. -- PIER")

    # Take the first (latest plant-by date) crop
    crop = crops[0]
    crop_name = crop.get("crop", "rescue")
    plant_by = crop.get("plant_by_date", "N/A")
    # Trim to ≤160 chars total
    base = f"{event_type.capitalize()}: {crop_name}. Plant by {plant_by}. -- PIER"
    return base[:155] + "..."  # ensure ≤160


def main():
    parser = argparse.ArgumentParser(description="SMS simulator for PIER demo")
    parser.add_argument("--lat", type=float, required=True, help="Field latitude")
    parser.add_argument("--lon", type=float, required=True, help="Field longitude")
    parser.add_argument("--date", type=str, required=True, help="ISO date YYYY-MM-DD")
    parser.add_argument("--demo-name", type=str, default="flood",
                        choices=["flood", "drought", "normal"],
                        help="Demo scenario")
    args = parser.parse_args()

    try:
        result = run_pier(
            lat=args.lat,
            lon=args.lon,
            current_date=args.date,
            demo_mode=True,
            demo_name=args.demo_name,
        )
        print(sms_format(result))
    except Exception as e:
        print(f"Error running PIER: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()