---
name: dlmm-meme-scanner
description: >
  Scans Meteora DLMM and DexScreener for the best Solana meme coin liquidity
  pools for fee-farming. Use when the user asks to scan for DLMM LP
  opportunities, find meme coins for fee farming, check Meteora pools, get LP
  ROI estimates, or run the meme coin scanner. Triggers on phrases like:
  "scan dlmm", "scan meme coins", "find LP pools", "best fee farming coins",
  "run the scanner", "DLMM opportunities", "check meteora pools".
---

# DLMM Meme Coin LP Scanner

Scans Meteora DLMM for top Solana meme coin pools suitable for fee-farming
via concentrated liquidity (DLMM) positions.

## Architecture

```
OLD (slow, ~45s):  DexScreener search × 10 + Meteora lookup × 20 = 30 API calls
NEW (fast, ~3s):   Meteora bulk fetch × 1 + DexScreener batch × 1 = 2 API calls
```

**Step 1 — Single Meteora bulk request**
`/pair/all_with_pagination?include_token_mints=<SOL>&sort_key=fees&limit=500`
Returns all SOL-paired DLMM pools pre-sorted by 24h fees. Each pool object
already contains: `fees_24h`, `fee_tvl_ratio`, `trade_volume_24h`, `liquidity`,
`bin_step`, `base_fee_percentage`, `apr`, `is_blacklisted`, `mint_x/y`.
No per-token follow-up calls needed.

**Step 2 — In-memory filtering (zero API calls)**
Apply TVL, min-fees, volume, and symbol filters entirely in Python.

**Step 3 — DexScreener batch enrichment (top-N only)**
`/tokens/v1/solana/{comma-separated-addresses}` — one call covers up to 28
tokens. Adds: `mcap`, `age_days`, `txns_1h`, `priceChange`, `dex_url`.
Skip with `--no-dex` for pure speed.

**Step 4 — Score, ROI, display**
Pure CPU — no network.

## How to invoke

```bash
python3 scanner.py                          # default: top 10, weekly ROI
python3 scanner.py --min-tvl 50000          # only pools with $50k+ TVL
python3 scanner.py --min-fees 500           # only pools earning $500+/day
python3 scanner.py --top-n 5               # show only top 5
python3 scanner.py --investment 5000        # ROI for a $5k position
python3 scanner.py --period daily           # highlight daily ROI (daily/weekly/monthly)
python3 scanner.py --fetch-limit 1000       # pull up to 1000 pools from Meteora
python3 scanner.py --no-dex                 # skip DexScreener, fastest mode (~1-2s)
python3 scanner.py --json                   # raw JSON output for piping
```

## Output format

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#1  🔥 HOT  │  BONK/SOL  │  Score: ████████████████░░░░ 82/100
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Token:               $BONK
  Meteora Pool:        5rCf1DM8LjK...
  Pair age:            4.2 days

  Pool TVL:            $184.2K
  24h Volume:          $921.0K
  24h Fees:            $4.3K
  Fee/TVL 24h:         2.31%  (est. APR: 843%)
  Bin Step:            100 bps
  Base Fee:            1.00%

  MCap:                $2.1M
  Vol/MCap:            0.44x
  Txns/hr:             213
  Price Δ 24h:         +18.4%

  DLMM Strategy:       Spot distribution ±25% — balanced risk/reward

    Daily ROI        (on $1.0K): ~$11 – $19
  ▶ Weekly ROI       (on $1.0K): ~$76 – $130
    Monthly ROI      (on $1.0K): ~$328 – $558
    Est. APR:         843.0%
    Your pool share:  0.54%
```

## Scoring rubric (0–100)

| Factor            | Weight | Ideal condition                           |
|-------------------|--------|-------------------------------------------|
| Fee/TVL 24h       | 30%    | ≥5% = 30pts, ≥3% = 25pts, ≥1% = 15pts   |
| Absolute fees 24h | 25%    | ≥$20k = 25pts, ≥$10k = 20pts, ≥$1k = 10pts |
| Liquidity         | 20%    | $100k–$500k sweet spot = 20pts            |
| Vol/MCap ratio    | 15%    | ≥0.5x = 15pts (needs DexScreener data)    |
| Pair age          | 10%    | 2–10 days = 10pts (needs DexScreener data)|

Red-flag deductions: fees declining (1h rate << daily avg), crashed price,
parabolic price, pair under 12h old.

## ROI estimation method

All three periods always shown. `--period` controls which is highlighted (▶).

```
share      = investment / (pool_tvl + investment)   # diluted share
daily_base = pool_24h_fees × share

daily_low    = daily_base × 1  × 0.50   # 50% in-range (conservative)
daily_high   = daily_base × 1  × 0.85   # 85% in-range (optimistic)
weekly_low   = daily_base × 7  × 0.50
weekly_high  = daily_base × 7  × 0.85
monthly_low  = daily_base × 30 × 0.50
monthly_high = daily_base × 30 × 0.85
apr_pct      = (daily_base × 365 / investment) × 100
```

Note: Does not account for impermanent loss. IL can exceed fee gains if price
moves >40% outside your LP range.

## Data sources

| Source | Endpoint | What it provides |
|--------|----------|------------------|
| Meteora DLMM | `/pair/all_with_pagination` | fees, tvl, volume, bin_step, all pool metrics |
| DexScreener  | `/tokens/v1/solana/{addrs}` | mcap, pair age, txns/hr, price change |

No API keys required. Both APIs are free and public.

## Dependencies

```
pip install requests
```

## Important warnings

- Meme coins carry extreme risk. Impermanent loss can wipe out fee gains.
- Always verify each token on rugcheck.xyz before entering.
- High fee/TVL ratios attract more capital, compressing future yields.
- This tool is for research only. Not financial advice.
