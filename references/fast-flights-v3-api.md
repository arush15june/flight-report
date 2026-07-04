# fast_flights v3 API Migration Notes

The `fast-flights` Python package underwent a breaking API change in v3.0.0.
The skill's original `search_flights.py` was written for v1/v2 and will fail
with `ImportError: cannot import name 'FlightData'` on v3+.

## v1/v2 API (OLD — does NOT work with fast-flights >= 3.0.0)

```python
from fast_flights import FlightData, Passengers, create_filter, get_flights_from_filter

flight_data = [
    FlightData(date="2026-07-06", from_airport="DEL", to_airport="MAA", max_stops=None)
]
flt = create_filter(
    flight_data=flight_data,
    trip="one-way",
    passengers=Passengers(adults=1),
    seat="economy",
    max_stops=None,
)
result = get_flights_from_filter(flt, currency="INR")

for f in result.flights:
    f.is_best  # bool
    f.name     # airline name
    f.price    # string like "₹9,996"
    f.departure, f.arrival  # strings
```

## v3 API (CURRENT — fast-flights >= 3.0.0)

```python
from fast_flights import FlightQuery, Passengers, create_filter, get_flights

flight_queries = [
    FlightQuery(date="2026-07-06", from_airport="DEL", to_airport="MAA", max_stops=None)
]
q = create_filter(
    flights=flight_queries,          # was flight_data=
    trip="one-way",
    passengers=Passengers(adults=1),
    seat="economy",
    currency="INR",                  # was a separate arg to get_flights_from_filter
    language="en-US",                # new param
    max_stops=None,
)
result = get_flights(q)              # was get_flights_from_filter(flt, currency=...)
```

### v3 Result Structure

`get_flights()` returns a `ResultList` (iterable, NOT having `.flights` attribute).
Each item is a `Flights` object:

| Field        | Type             | Notes                                    |
|--------------|------------------|------------------------------------------|
| `.price`     | int              | Numeric price (e.g. 9996), not a string  |
| `.airlines`  | list[str]        | Airline names                            |
| `.type`      | str              | Airline code (e.g. "6E" for IndiGo)      |
| `.flights`   | list[SingleFlight] | The legs of this flight option        |
| `.carbon`    | CarbonEmission   | Carbon data                              |

Each `SingleFlight` (leg):

| Field          | Type            | Notes                                      |
|----------------|-----------------|--------------------------------------------|
| `.from_airport`| Airport        | Has `.name` and `.code`                    |
| `.to_airport`  | Airport        | Has `.name` and `.code`                    |
| `.departure`   | SimpleDatetime | `.date=[Y,M,D]`, `.time=[H,M]`             |
| `.arrival`     | SimpleDatetime | `.date=[Y,M,D]`, `.time=[H,M]`             |
| `.duration`    | int            | Duration in minutes                        |
| `.plane_type`  | str            | e.g. "Airbus A321neo"                      |

### Key Differences Summary

| Concept              | v1/v2                        | v3+                              |
|----------------------|------------------------------|----------------------------------|
| Flight data class    | `FlightData`                 | `FlightQuery`                    |
| Filter param name    | `flight_data=`               | `flights=`                       |
| Fetch function       | `get_flights_from_filter()`  | `get_flights()`                  |
| Currency             | arg to fetch function        | arg to `create_filter()`         |
| Language             | not available                | arg to `create_filter()`         |
| Result type          | object with `.flights` list  | `ResultList` (iterable of `Flights`) |
| Price                | string (e.g. "₹9,996")      | int (e.g. 9996)                  |
| Airline name         | `f.name`                     | `item.airlines` (list) / `item.type` |
| Departure/arrival    | string fields on flight      | `SimpleDatetime` objects on legs  |
| Multi-leg info       | `f.stops` (int)              | `len(item.flights) - 1`          |

### Gotchas

1. **`ResultList` has no `.flights` attribute.** You must iterate it directly:
   `for item in result:` — each `item` is a `Flights` object that HAS `.flights`.

2. **Some departure/arrival times may be `None`** in the v3 API. The
   `SimpleDatetime` object may be present but have empty/None `.time`. Always
   null-check when formatting times.

3. **`typing_extensions` is a transitive dependency** but not always installed
   automatically. If you see `ModuleNotFoundError: No module named
   'typing_extensions'`, install it: `uv pip install typing_extensions`.

4. **Round-trip in v3:** pass multiple `FlightQuery` objects in the `flights=`
   list and set `trip="round-trip"`. The result will contain combined round-trip
   options.
