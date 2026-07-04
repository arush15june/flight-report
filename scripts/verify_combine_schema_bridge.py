#!/usr/bin/env python3
"""Ad-hoc verifier for combine_flights.py schema bridging.

Purpose:
- confirm combine_flights.py accepts both legacy search output
  (price_numeric, duration)
- and fast-flights v3 output (price, duration_mins)
- in the same run.

Run:
  python scripts/verify_combine_schema_bridge.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
COMBINE = SKILL_DIR / "scripts" / "combine_flights.py"

OUTBOUND = {
    "daily_results": [
        {
            "date": "2026-07-06",
            "flights": [
                {
                    "airline": "IndiGo",
                    "departure": "07:30",
                    "arrival": "10:20",
                    "duration_mins": 170,
                    "price": 12000,
                },
                {
                    "airline": "LegacyAir",
                    "departure": "08:00",
                    "arrival": "11:00",
                    "duration": "3h 0m",
                    "price_numeric": 15000,
                },
            ],
        }
    ]
}

RETURNS = {
    "daily_results": [
        {
            "date": "2026-07-06",
            "flights": [
                {
                    "airline": "IndiGo",
                    "departure": "19:00",
                    "arrival": "21:55",
                    "duration_mins": 175,
                    "price": 11000,
                },
                {
                    "airline": "LegacyAir",
                    "departure": "20:00",
                    "arrival": "23:00",
                    "duration": "3h 0m",
                    "price_numeric": 16000,
                },
            ],
        }
    ]
}


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hermes-verify-") as td:
        td = Path(td)
        out_json = td / "out.json"
        ret_json = td / "ret.json"
        combo_json = td / "combo.json"
        out_json.write_text(json.dumps(OUTBOUND), encoding="utf-8")
        ret_json.write_text(json.dumps(RETURNS), encoding="utf-8")

        cmd = [
            sys.executable,
            str(COMBINE),
            "--outbound-json",
            str(out_json),
            "--return-json",
            str(ret_json),
            "--min-days",
            "1",
            "--max-days",
            "1",
            "--filter-complete",
            "--output",
            str(combo_json),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print("FAIL: combine_flights.py exited non-zero")
            if res.stdout:
                print(res.stdout)
            if res.stderr:
                print(res.stderr)
            return 1

        data = json.loads(combo_json.read_text(encoding="utf-8"))
        combos = data["combos_sorted"]
        assert len(combos) == 4, f"expected 4 combos, got {len(combos)}"

        cheapest = combos[0]
        assert cheapest["ticket_price"] == 23000, cheapest
        assert cheapest["total_price"] == 25000, cheapest
        assert cheapest["outbound"]["duration"] == "2h 50m", cheapest
        assert cheapest["return"]["duration"] == "2h 55m", cheapest

        legacy_combo = [
            c
            for c in combos
            if c["outbound"]["airline"] == "LegacyAir"
            and c["return"]["airline"] == "LegacyAir"
        ]
        assert legacy_combo, "missing legacy+legacy combo"
        assert legacy_combo[0]["ticket_price"] == 31000, legacy_combo[0]
        assert legacy_combo[0]["outbound"]["duration"] == "3h 0m", legacy_combo[0]

        print(
            "PASS: combine_flights.py handles both v3 and legacy schemas in one run"
        )
        print(
            f"Generated {len(combos)} combos; "
            f"cheapest ticket_price={cheapest['ticket_price']} "
            f"total_price={cheapest['total_price']}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
