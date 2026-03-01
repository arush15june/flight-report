#!/usr/bin/env python3
"""Search Google Flights using fast-flights and output structured JSON results."""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta


def parse_args():
    parser = argparse.ArgumentParser(description="Search Google Flights via fast-flights")
    parser.add_argument("--origin", required=True, help="Origin IATA code (e.g. TPE)")
    parser.add_argument("--destination", required=True, help="Destination IATA code (e.g. NRT)")
    parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--return-offset", type=int, default=None,
                        help="Days after departure for return flight (round-trip only)")
    parser.add_argument("--nonstop", action="store_true", help="Nonstop flights only")
    parser.add_argument("--trip-type", choices=["one-way", "round-trip"], default="one-way",
                        help="Trip type (default: one-way)")
    parser.add_argument("--seat", choices=["economy", "premium-economy", "business", "first"],
                        default="economy", help="Seat class (default: economy)")
    parser.add_argument("--adults", type=int, default=1, help="Number of adults (default: 1)")
    parser.add_argument("--sample-mode", type=int, default=3,
                        help="Sample every N days (default: 3)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Delay between requests in seconds (default: 2.0)")
    parser.add_argument("--currency", default="TWD", help="Currency code (default: TWD)")
    parser.add_argument("--output", default=None, help="Output JSON file path (default: stdout)")
    return parser.parse_args()


def search_single_date(origin, destination, date_str, trip_type, return_date_str,
                       nonstop, seat, adults, currency):
    """Search flights for a single date. Returns a dict with results or error."""
    from fast_flights import FlightData, Passengers, create_filter, get_flights_from_filter

    max_stops = 0 if nonstop else None

    flight_data = [
        FlightData(date=date_str, from_airport=origin, to_airport=destination, max_stops=max_stops)
    ]

    if trip_type == "round-trip" and return_date_str:
        flight_data.append(
            FlightData(date=return_date_str, from_airport=destination, to_airport=origin,
                       max_stops=max_stops)
        )

    try:
        flt = create_filter(
            flight_data=flight_data,
            trip=trip_type,
            passengers=Passengers(adults=adults),
            seat=seat,
            max_stops=max_stops,
        )
        result = get_flights_from_filter(flt, currency=currency)

        flights = []
        for f in result.flights:
            price_num = None
            if f.price:
                cleaned = f.price.replace(",", "").replace("$", "").replace("NT", "")
                cleaned = "".join(c for c in cleaned if c.isdigit() or c == ".")
                try:
                    price_num = float(cleaned)
                except ValueError:
                    pass

            flights.append({
                "is_best": f.is_best,
                "airline": f.name,
                "departure": f.departure,
                "arrival": f.arrival,
                "arrival_time_ahead": f.arrival_time_ahead,
                "duration": f.duration,
                "stops": f.stops,
                "delay": f.delay,
                "price": f.price,
                "price_numeric": price_num,
            })

        return {
            "date": date_str,
            "return_date": return_date_str if trip_type == "round-trip" else None,
            "current_price": result.current_price,
            "flights": flights,
        }
    except Exception as e:
        return {
            "date": date_str,
            "return_date": return_date_str if trip_type == "round-trip" else None,
            "error": str(e),
            "flights": [],
        }


def generate_sample_dates(start_date, end_date, sample_every):
    """Generate dates to sample between start and end, every N days."""
    dates = []
    current = start_date
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=sample_every)
    return dates


def main():
    args = parse_args()

    start_date = datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end_date, "%Y-%m-%d").date()

    if end_date < start_date:
        print("Error: end-date must be after start-date", file=sys.stderr)
        sys.exit(1)

    sample_dates = generate_sample_dates(start_date, end_date, args.sample_mode)

    print(f"Searching {args.origin} → {args.destination} ({args.trip_type})", file=sys.stderr)
    print(f"Date range: {args.start_date} to {args.end_date}", file=sys.stderr)
    print(f"Sampling {len(sample_dates)} dates (every {args.sample_mode} days)", file=sys.stderr)
    if args.nonstop:
        print("Filter: nonstop only", file=sys.stderr)
    print(f"Currency: {args.currency}", file=sys.stderr)
    print("---", file=sys.stderr)

    all_results = []
    for i, date in enumerate(sample_dates):
        date_str = date.strftime("%Y-%m-%d")
        return_date_str = None
        if args.trip_type == "round-trip" and args.return_offset:
            return_date = date + timedelta(days=args.return_offset)
            return_date_str = return_date.strftime("%Y-%m-%d")

        print(f"[{i+1}/{len(sample_dates)}] Searching {date_str}...", file=sys.stderr)

        result = search_single_date(
            origin=args.origin,
            destination=args.destination,
            date_str=date_str,
            trip_type=args.trip_type,
            return_date_str=return_date_str,
            nonstop=args.nonstop,
            seat=args.seat,
            adults=args.adults,
            currency=args.currency,
        )
        all_results.append(result)

        if result.get("error"):
            print(f"  Error: {result['error']}", file=sys.stderr)
        else:
            n = len(result["flights"])
            cheapest = None
            for f in result["flights"]:
                if f["price_numeric"] is not None:
                    if cheapest is None or f["price_numeric"] < cheapest:
                        cheapest = f["price_numeric"]
            price_info = f", cheapest: {cheapest}" if cheapest else ""
            print(f"  Found {n} flights{price_info}", file=sys.stderr)

        if i < len(sample_dates) - 1:
            time.sleep(args.delay)

    # Collect all flights with their search date for sorting, dedup by key fields
    all_flights = []
    seen = set()
    for r in all_results:
        for f in r["flights"]:
            f["search_date"] = r["date"]
            if r.get("return_date"):
                f["return_date"] = r["return_date"]
            # Deduplicate: same date + airline + departure + price
            key = (r["date"], f["airline"], f["departure"], f["price"])
            if key not in seen:
                seen.add(key)
                all_flights.append(f)

    # Sort by price (cheapest first), flights without price go to end
    all_flights.sort(key=lambda x: x["price_numeric"] if x["price_numeric"] is not None else float("inf"))

    output = {
        "query": {
            "origin": args.origin,
            "destination": args.destination,
            "start_date": args.start_date,
            "end_date": args.end_date,
            "trip_type": args.trip_type,
            "nonstop": args.nonstop,
            "seat": args.seat,
            "currency": args.currency,
            "adults": args.adults,
        },
        "search_summary": {
            "total_dates_searched": len(sample_dates),
            "total_flights_found": len(all_flights),
            "dates_with_errors": sum(1 for r in all_results if r.get("error")),
        },
        "daily_results": all_results,
        "all_flights_sorted_by_price": all_flights,
    }

    json_str = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(json_str)
        print(f"\nResults saved to {args.output}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
