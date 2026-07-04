#!/usr/bin/env python3
"""Combine outbound and return flight search results into round-trip combinations."""

import argparse
import json
import sys
from datetime import datetime, timedelta


def parse_args():
    parser = argparse.ArgumentParser(
        description="Combine outbound + return flight JSONs into round-trip combos"
    )
    parser.add_argument("--outbound-json", required=True,
                        help="Path to outbound (departure) search results JSON")
    parser.add_argument("--return-json", required=True,
                        help="Path to return search results JSON")
    parser.add_argument("--min-days", type=int, required=True,
                        help="Minimum trip days (inclusive, counting both departure and return day)")
    parser.add_argument("--max-days", type=int, required=True,
                        help="Maximum trip days (inclusive, counting both departure and return day)")
    parser.add_argument("--arrival-before", default=None,
                        help="Filter outbound flights arriving before this time (e.g. 12:00)")
    parser.add_argument("--baggage-cost", type=int, default=2000,
                        help="Round-trip baggage cost in TWD (default: 2000)")
    parser.add_argument("--filter-complete", action="store_true",
                        help="Only keep flights with complete info (airline/departure/arrival non-empty)")
    parser.add_argument("--output", default=None,
                        help="Output JSON file path (default: stdout)")
    return parser.parse_args()


def parse_time(time_str):
    """Parse a time string like '10:30 AM', '14:00', or '6:05 AM on Wed, Apr 1' into minutes since midnight."""
    if not time_str:
        return None
    time_str = time_str.strip()
    # Strip trailing " on ..." suffix (e.g. "6:05 AM on Wed, Apr 1")
    if " on " in time_str:
        time_str = time_str.split(" on ")[0].strip()
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M"):
        try:
            t = datetime.strptime(time_str, fmt)
            return t.hour * 60 + t.minute
        except ValueError:
            continue
    return None


def is_flight_complete(flight):
    """Check if a flight has complete info (airline, departure, arrival all non-empty)."""
    return bool(flight.get("airline")) and bool(flight.get("departure")) and bool(flight.get("arrival"))


def get_price(flight):
    """Return a numeric price from either legacy or v3 search output."""
    price = flight.get("price_numeric")
    if price is not None:
        return price
    price = flight.get("price")
    if isinstance(price, (int, float)):
        return price
    return None


def get_duration(flight):
    """Return a duration string from either legacy or v3 search output."""
    duration = flight.get("duration")
    if duration:
        return duration
    mins = flight.get("duration_mins")
    if isinstance(mins, int):
        return f"{mins // 60}h {mins % 60}m"
    return None


def extract_flights_by_date(results_json):
    """Extract flights grouped by search_date from a search results JSON."""
    flights_by_date = {}
    for day_result in results_json.get("daily_results", []):
        date_str = day_result.get("date")
        if not date_str or day_result.get("error"):
            continue
        flights = day_result.get("flights", [])
        if date_str not in flights_by_date:
            flights_by_date[date_str] = []
        for f in flights:
            f_copy = dict(f)
            f_copy["search_date"] = date_str
            flights_by_date[date_str].append(f_copy)
    return flights_by_date


def count_workdays(start_date, end_date, outbound_dep_time_minutes=None):
    """Count workdays that need leave for a trip.

    Rules:
    - Departure day: counts as a leave day if it's a weekday AND the outbound
      flight departs before 22:00 (you can't work that day).
    - Days in between (start_date+1 to end_date-1): all weekdays count.
    - Return day: does NOT count (you arrive back and it's travel, not leave).

    Args:
        start_date: departure date
        end_date: return date
        outbound_dep_time_minutes: outbound departure time in minutes since midnight
            (e.g. 720 = 12:00). If None or >= 1320 (22:00), departure day is not counted.
    """
    workdays = 0

    # Departure day
    if start_date.weekday() < 5:  # weekday
        if outbound_dep_time_minutes is not None and outbound_dep_time_minutes < 22 * 60:
            workdays += 1
        elif outbound_dep_time_minutes is None:
            # Default: assume departure day needs leave
            workdays += 1

    # Days in between (exclusive of both departure and return day)
    current = start_date + timedelta(days=1)
    while current < end_date:
        if current.weekday() < 5:  # Mon=0 .. Fri=4
            workdays += 1
        current += timedelta(days=1)

    return workdays


def main():
    args = parse_args()

    # Load JSON files
    with open(args.outbound_json, "r", encoding="utf-8") as f:
        outbound_data = json.load(f)
    with open(args.return_json, "r", encoding="utf-8") as f:
        return_data = json.load(f)

    # Parse arrival_before threshold
    arrival_limit = None
    if args.arrival_before:
        arrival_limit = parse_time(args.arrival_before)
        if arrival_limit is None:
            print(f"Warning: could not parse --arrival-before '{args.arrival_before}', ignoring",
                  file=sys.stderr)

    # Extract flights by date
    outbound_by_date = extract_flights_by_date(outbound_data)
    return_by_date = extract_flights_by_date(return_data)

    outbound_count = sum(len(v) for v in outbound_by_date.values())
    return_count = sum(len(v) for v in return_by_date.values())
    print(f"Outbound: {len(outbound_by_date)} dates, {outbound_count} flights", file=sys.stderr)
    print(f"Return: {len(return_by_date)} dates, {return_count} flights", file=sys.stderr)

    # Build combinations
    combos = []
    for out_date_str, out_flights in outbound_by_date.items():
        out_date = datetime.strptime(out_date_str, "%Y-%m-%d").date()

        for out_f in out_flights:
            # Filter incomplete flights
            if args.filter_complete and not is_flight_complete(out_f):
                continue

            # Filter by price
            out_price = get_price(out_f)
            if out_price is None:
                continue

            # Filter by arrival time
            if arrival_limit is not None:
                arr_time = parse_time(out_f.get("arrival"))
                if arr_time is not None and arr_time > arrival_limit:
                    continue

            # Try matching return flights within day range
            for days in range(args.min_days, args.max_days + 1):
                # days is inclusive (頭尾都算), so nights = days - 1
                # e.g. 4 days = depart day1, return day4, 3 nights in between
                ret_date = out_date + timedelta(days=days - 1)
                ret_date_str = ret_date.strftime("%Y-%m-%d")

                if ret_date_str not in return_by_date:
                    continue

                for ret_f in return_by_date[ret_date_str]:
                    # Filter incomplete return flights
                    if args.filter_complete and not is_flight_complete(ret_f):
                        continue

                    ret_price = get_price(ret_f)
                    if ret_price is None:
                        continue

                    ticket_price = out_price + ret_price
                    total_price = ticket_price + args.baggage_cost
                    nights = days - 1
                    out_dep_minutes = parse_time(out_f.get("departure"))
                    workdays = count_workdays(out_date, ret_date, out_dep_minutes)

                    combos.append({
                        "total_price": total_price,
                        "ticket_price": ticket_price,
                        "baggage_cost": args.baggage_cost,
                        "days": days,
                        "nights": nights,
                        "workdays": workdays,
                        "outbound": {
                            "date": out_date_str,
                            "airline": out_f.get("airline"),
                            "departure": out_f.get("departure"),
                            "arrival": out_f.get("arrival"),
                            "duration": get_duration(out_f),
                            "price": out_price,
                        },
                        "return": {
                            "date": ret_date_str,
                            "airline": ret_f.get("airline"),
                            "departure": ret_f.get("departure"),
                            "arrival": ret_f.get("arrival"),
                            "duration": get_duration(ret_f),
                            "price": ret_price,
                        },
                    })

    # Sort by total price
    combos.sort(key=lambda x: x["total_price"])

    print(f"Generated {len(combos)} combinations", file=sys.stderr)

    # Best per day count
    best_per_days = {}
    for c in combos:
        d = str(c["days"])
        if d not in best_per_days:
            best_per_days[d] = c

    # Best per workdays
    best_per_workdays = {}
    for c in combos:
        w = str(c["workdays"])
        if w not in best_per_workdays:
            best_per_workdays[w] = c

    output = {
        "combos_sorted": combos,
        "best_per_days": best_per_days,
        "best_per_workdays": best_per_workdays,
        "summary": {
            "total_combos": len(combos),
            "outbound_count": outbound_count,
            "return_count": return_count,
        },
    }

    json_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"Results saved to {args.output}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
