---
name: flight-report
description: >
  Search Google Flights and generate a structured price comparison report.
  Triggers on: cheap flights, flight search, nonstop flights, flight comparison, airfare,
  flight report, compare flights, best flights, flight deals
user_invocable: true
---

# Flight Report Skill

You are a flight search assistant. When the user asks about flights, airfare, or ticket prices, follow these steps to produce a comprehensive price comparison report.

## Prerequisites & Setup

The search scripts depend on the `fast-flights` Python package. Use `uv` (never `pip3 --break-system-packages`) to manage Python environments:

```bash
# Create a venv once per session (or reuse if already present)
uv venv /tmp/flights-venv
uv pip install --python /tmp/flights-venv/bin/python fast-flights typing_extensions
```

Then run scripts with `/tmp/flights-venv/bin/python` instead of `python` or `python3`.

### Script Versions

| Script | API version | When to use |
|--------|------------|-------------|
| `scripts/search_flights.py` | v1/v2 (legacy) | Only if fast-flights < 3.0.0 is pinned |
| `scripts/search_flights_v3.py` | v3+ (current) | Default — use with fast-flights >= 3.0.0 |

If you see `ImportError: cannot import name 'FlightData'`, you're on v3+ but
running the legacy script — switch to `search_flights_v3.py`.
See `references/fast-flights-v3-api.md` for full v3 API migration details.

## Step 1: Parse the User Query

Extract the following from the user's natural language query (Chinese or English):
- **Origin**: departure city or airport
- **Destination**: arrival city or airport
- **Date range**: start and end dates (if the user says "三月到五月", interpret as the full months)
- **Trip type**: one-way, round-trip, or flexible-roundtrip
  - 來回 = round-trip; default to one-way if not specified
  - If the user specifies a **day range** (e.g. 「玩4~7天」「4到5天」), use **flexible-roundtrip**
- **Return offset**: if round-trip (fixed), how many days for the return (default: 7 days)
- **Flexible day range**: if flexible-roundtrip, extract min_days and max_days
  - 天數定義：含頭含尾（出發日 + 回程日都算）。「玩4天」= 出發日算第1天，回程日算第4天，住3晚
  - 例：「4~7天」→ min_days=4, max_days=7
- **Nonstop**: whether direct flights only (直飛 = nonstop)
- **Airline exclusions / preferences**: capture explicit bans or preferences (e.g. "don't take SpiceJet", "avoid red-eyes", "prefer Air India over IndiGo") and apply them before ranking
- **Outbound arrival time limit**: e.g. 「中午前到」→ arrival_before=12:00
- **Baggage needs**: LCC routes typically need checked baggage (default round-trip: NT$2,000)
- **Seat class**: economy (default), business, first
- **Number of adults**: default 1

If any critical info is missing (origin or destination), ask the user before proceeding.

## Step 2: Map City Names to IATA Codes

Use the skill-local reference file `references/airport-codes.md` (via `skill_view(name='flight-report', file_path='references/airport-codes.md')`) to convert city names to IATA airport codes.

Common mappings:
- 桃園/台北 → TPE
- 東京成田 → NRT, 東京羽田 → HND
- 大阪/關西 → KIX
- 福岡 → FUK
- 首爾/仁川 → ICN
- 曼谷 → BKK
- 新加坡 → SIN

If the city is ambiguous (e.g. "東京" could be NRT or HND), default to the main international airport (NRT for 東京) and mention the assumption.

## Step 3: Run Flight Search

Execute the search script using the Bash tool. Use `search_flights_v3.py` (the
default for fast-flights >= 3.0.0) and run it with the uv venv python:

```bash
SKILL_DIR=/path/to/flight-report
/tmp/flights-venv/bin/python "$SKILL_DIR/scripts/search_flights_v3.py" \
  --origin {ORIGIN} \
  --destination {DEST} \
  --start-date {YYYY-MM-DD} \
  --end-date {YYYY-MM-DD} \
  --trip-type {one-way|round-trip} \
  --seat {economy|business|first} \
  --adults {N} \
  --currency {CURRENCY} \
  --sample-mode 3 \
  --delay 2 \
  --output /tmp/flight_results.json \
  {--nonstop if requested} \
  {--return-offset N if round-trip}
```

Set `CURRENCY` to the user's requested market (`INR` for India, `TWD` for Taiwan, etc.).

**Important notes:**
- The script samples every 3 days by default. For short ranges (< 14 days), use `--sample-mode 1`.
- For large date ranges (> 3 months), use `--sample-mode 7` to reduce requests.
- The script outputs progress to stderr and results to the JSON file.
- If the script fails or returns errors, check if the IATA codes are correct and try with `--sample-mode 7` for a smaller sample.

### Step 3b: Flexible Round-Trip Search (Independent One-Way Combination)

When the user specifies a flexible day range (trip_type = flexible-roundtrip), use the following flow instead of Step 3:

1. **Search outbound (one-way)**: origin → destination, across the user's date range
2. **Search return (one-way)**: destination → origin, date range = outbound_start + (min_days-1) ~ outbound_end + (max_days-1)
3. **Run both searches concurrently** using parallel tool calls / background execution if needed. Use the same v3 script for both directions:

```bash
SKILL_DIR=/path/to/flight-report
# Outbound search
/tmp/flights-venv/bin/python "$SKILL_DIR/scripts/search_flights_v3.py" \
  --origin {ORIGIN} --destination {DEST} \
  --start-date {OUT_START} --end-date {OUT_END} \
  --trip-type one-way --sample-mode 1 --delay 2 \
  --currency {CURRENCY} --output /tmp/out_daily.json \
  {--nonstop if requested}

# Return search
/tmp/flights-venv/bin/python "$SKILL_DIR/scripts/search_flights_v3.py" \
  --origin {DEST} --destination {ORIGIN} \
  --start-date {RET_START} --end-date {RET_END} \
  --trip-type one-way --sample-mode 1 --delay 2 \
  --currency {CURRENCY} --output /tmp/ret_daily.json \
  {--nonstop if requested}
```

4. **Combine results** using the combination script:

```bash
/tmp/flights-venv/bin/python "$SKILL_DIR/scripts/combine_flights.py" \
  --outbound-json /tmp/out_daily.json \
  --return-json /tmp/ret_daily.json \
  --min-days {MIN_DAYS} --max-days {MAX_DAYS} \
  --filter-complete \
  --baggage-cost {BAGGAGE_COST} \
  {--arrival-before HH:MM if specified} \
  --output /tmp/combo_results.json
```

`combine_flights.py` now accepts both legacy `search_flights.py` output and v3 `search_flights_v3.py` output (`price_numeric` vs `price`, `duration` vs `duration_mins`).

**⚠️ Sample-mode caveat for flexible round-trip:**
When both outbound and return use `--sample-mode 3`, the possible day counts are limited to `offset + 3n` values, so some trip lengths will have zero combinations. For flexible round-trip searches, **always use `--sample-mode 1`** and limit the date range to one month or less. For larger ranges, split into monthly batches.

## Step 4: Read and Analyze Results

Read the output JSON file with Hermes `read_file` (preferred) or a shell reader if you're outside Hermes:
```bash
read_file /tmp/flight_results.json
# or for flexible round-trip:
read_file /tmp/combo_results.json
```

### Data Quality Filtering

The scraper sometimes returns entries with a price but no flight details (airline, departure, and arrival are empty). These incomplete entries must be filtered out before analysis to avoid recommending flights with no actionable information.

- For flexible round-trip: use `--filter-complete` in `combine_flights.py` (handles this automatically)
- For one-way / fixed round-trip: manually skip any flight where `airline`, `departure`, or `arrival` is null/empty

### Analysis

Analyze the data:
- Sort flights by price to find the cheapest options
- Group by month for monthly summaries
- Identify which day of the week tends to be cheapest
- Note any "is_best" flights (Google's recommended picks)

### Same-Day Outbound + Night Return Requests

When the user asks for a same-day trip such as "go Monday morning and come back at night", treat this as a **combination-ranking task**, not just two separate cheapest-flight lists.

1. Search both directions as one-way on the same date.
2. Filter out incomplete rows first (`departure`/`arrival` missing).
3. Apply hard constraints before ranking:
   - nonstop only if requested
   - exclude banned airlines explicitly named by the user
   - enforce morning outbound / evening-or-night return windows from the request
4. Build viable same-day combinations with a minimum ground buffer (default 3 hours unless the user asks for tighter timing).
5. Present **multiple options**, labelled by tradeoff, for example:
   - cheapest direct combo
   - better timing / later return
   - latest usable return
6. If true night-return options are sparse or much more expensive, say so clearly and include the closest practical direct alternatives instead of pretending there are many night options.

This pattern is especially important on domestic India routes where one morning nonstop outbound may combine with only a small number of evening nonstop returns.

## Step 5: Supplement with Web Search (Optional)

Use WebSearch to find additional context:
- Current airline baggage policies for the route
- Any seasonal travel advisories
- Alternative airport options

Keep this brief — the main value is in the flight data.

## Step 6: Generate the Report

Follow the template in `references/report-template.md` (load via `skill_view(name='flight-report', file_path='references/report-template.md')`) to produce the final report in the **user's language**. Use Traditional Chinese only when the user is writing in Chinese or explicitly asks for it.

- For **one-way / fixed round-trip**: use the standard report template (single-direction table)
- For **flexible round-trip**: use the **來回組合報告模板** (round-trip combination template) in the same file

Key formatting rules:
- Use a Markdown table for the price comparison
- Show TOP 10 cheapest flights (or combinations for flexible round-trip)
- For flexible round-trip, include: 天（含頭含尾）/夜、請假天數、行李費、總成本
- **請假天數算法**：去程當天一律算請假（除非出發時間在晚上 22:00 之後），回程當天不算請假。中間的平日全部算請假
- Include "各天數最便宜" and "依請假天數推薦" sections for flexible round-trip
- Include monthly price summaries (for one-way/fixed round-trip)
- Add actionable booking advice
- Include Google Flights and Skyscanner quick links
- All prices in TWD unless the user specifies otherwise

## Error Handling

- If `fast-flights` fails on a particular date, the script logs the error and continues with other dates
- If ALL dates fail, suggest the user try:
  1. Different date range
  2. Removing the nonstop filter
  3. Checking if the route exists on Google Flights
- If the IATA code mapping is unclear, ask the user to confirm the airport
