# Flight Report

A Hermes/Claude-style skill for searching Google Flights and producing structured airfare comparison reports.

## What this skill does

This skill helps an agent turn natural-language flight requests into repeatable searches and clean comparison reports.

Key capabilities:
- Understands flight requests in English or Chinese
- Maps city names to IATA airport codes automatically
- Supports three search modes:
  - **One-way**
  - **Fixed round-trip** (return after a specific number of days)
  - **Flexible round-trip** (search a range of trip lengths and combine outbound/return options)
- Supports outbound arrival-time filters such as "arrive before noon"
- Adds baggage cost for low-cost-carrier comparisons when needed
- Calculates leave days for trip planning
- Filters out incomplete scraped flight rows automatically
- Produces markdown reports suitable for sharing with users

## Directory structure

```text
flight-report/
├── SKILL.md                              # Main skill instructions and workflow
├── README.md                             # Human-readable overview and setup guide
├── scripts/
│   ├── search_flights.py                 # Legacy Google Flights search script
│   ├── search_flights_v3.py              # Current Google Flights search script for fast-flights v3+
│   ├── combine_flights.py                # Combine outbound and return searches into ranked trip options
│   └── verify_combine_schema_bridge.py   # Validation helper for schema compatibility
├── references/
│   ├── airport-codes.md                  # Common city/IATA mapping reference
│   ├── report-template.md                # Report templates
│   └── fast-flights-v3-api.md            # Notes on the v3 API migration
└── evals/
    └── evals.json                        # Example evaluation cases
```

## Installation

This skill uses the `fast-flights` Python package.

Use `uv` to create an isolated environment:

```bash
uv venv /tmp/flights-venv
uv pip install --python /tmp/flights-venv/bin/python fast-flights typing_extensions
```

Run scripts with the venv Python:

```bash
/tmp/flights-venv/bin/python ...
```

## How to use the skill

### As a Hermes skill

Place the skill directory under your Hermes skills tree and load it through Hermes tooling. The operational instructions live in `SKILL.md`.

Example user requests:

```text
Find cheap nonstop flights from Delhi to Chennai on Monday morning and return at night
Taipei to Fukuoka in April, nonstop, cheapest round-trip
台北到大阪六月來回機票，幫我比價
桃園到福岡直飛便宜機票，玩 4~5 天
```

### As standalone scripts

#### Search flights

```bash
SKILL_DIR=/home/fourcore/.hermes/profiles/sales/skills/productivity/flight-report
/tmp/flights-venv/bin/python "$SKILL_DIR/scripts/search_flights_v3.py" \
  --origin TPE \
  --destination KIX \
  --start-date 2026-04-01 \
  --end-date 2026-04-30 \
  --trip-type one-way \
  --nonstop \
  --sample-mode 1 \
  --delay 2 \
  --currency TWD \
  --output /tmp/outbound.json
```

#### Combine outbound and return options

```bash
SKILL_DIR=/home/fourcore/.hermes/profiles/sales/skills/productivity/flight-report
/tmp/flights-venv/bin/python "$SKILL_DIR/scripts/combine_flights.py" \
  --outbound-json /tmp/outbound.json \
  --return-json /tmp/return.json \
  --min-days 4 \
  --max-days 5 \
  --arrival-before 12:00 \
  --baggage-cost 2000 \
  --filter-complete \
  --output /tmp/combos.json
```

## Script selection

| Script | Use when |
|---|---|
| `scripts/search_flights.py` | You intentionally need the legacy fast-flights v1/v2 flow |
| `scripts/search_flights_v3.py` | Default choice for fast-flights v3+ |
| `scripts/combine_flights.py` | You need to rank paired outbound/return options |

If you see an error such as `ImportError: cannot import name 'FlightData'`, switch from the legacy script to `search_flights_v3.py`.

## `combine_flights.py` arguments

| Argument | Description |
|---|---|
| `--outbound-json` | Outbound search-result JSON file |
| `--return-json` | Return search-result JSON file |
| `--min-days` | Minimum trip length, counted inclusively |
| `--max-days` | Maximum trip length, counted inclusively |
| `--arrival-before` | Latest allowed outbound arrival time, for example `12:00` |
| `--baggage-cost` | Round-trip baggage cost to add to comparisons |
| `--filter-complete` | Remove rows that are missing key flight details |
| `--output` | Output file path |

## Trip-length rules

This skill uses **inclusive day counting**:
- Departure day counts as day 1
- Return day counts as the final day
- Example: depart on 2026-04-10 and return on 2026-04-13 = **4 days / 3 nights**

For leave-day estimation:
- The outbound day counts as a leave day unless the user departs very late at night
- The return day does not count as a leave day

## Notes on data quality

Google Flights scraping can sometimes return rows that contain a price but have missing timing or airline details. Those rows should not be recommended to users. The skill workflow explicitly filters incomplete rows before ranking results.

This matters most for:
- same-day outbound + night-return requests
- nonstop-only searches
- flexible round-trip combinations

## License

MIT
