#!/usr/bin/env python3
"""
OpenClaw DLMM Meme Scanner
Single-request architecture: fetches all SOL-paired DLMM pools from Meteora
in one call, filters and scores in-memory, optionally enriches the top-N
results with DexScreener for mcap/age/txn data.

No API key required. Typical runtime: 2-4 seconds.
"""

import sys
import json
import time
import argparse
import datetime
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ImportError:
    print("Missing dependency. Run: pip install requests")
    sys.exit(1)

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DEX_API     = "https://api.dexscreener.com"
METEORA_API = "https://dlmm-api.meteora.ag"
SOL_MINT    = "So11111111111111111111111111111111111111112"
TIMEOUT     = 20
MAX_RETRIES = 1   # get() handles 429 backoff itself

# In-range time assumptions for ROI bounds
ROI_LOW_FACTOR  = 0.50   # 50% of time price stays inside range (conservative)
ROI_HIGH_FACTOR = 0.85   # 85% in-range (optimistic)

SKIP_SYMBOLS = {
    "SOL", "WSOL", "MSOL", "JITOSOL", "BSOL", "JPOOL",
    "USDC", "USDT", "USDE", "DAI", "BUSD", "TUSD", "FRAX", "USDH", "UXD",
}

COLORS = {
    "reset": "\033[0m", "bold":  "\033[1m",
    "green": "\033[92m", "amber": "\033[93m",
    "red":   "\033[91m", "cyan":  "\033[96m",
    "gray":  "\033[90m", "white": "\033[97m",
}

def c(color: str, text: str) -> str:
    if sys.stdout.isatty():
        return COLORS.get(color, "") + text + COLORS["reset"]
    return text

# ─── HTTP CLIENT ──────────────────────────────────────────────────────────────

def make_session() -> requests.Session:
    s = requests.Session()
    retry = Retry(total=MAX_RETRIES, backoff_factor=0.5,
                  status_forcelist=[500, 502, 503])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": "OpenClaw-DLMM-Scanner/2.0", "Accept": "application/json"})
    return s

SESSION = make_session()

def get(url: str, params: dict = None, _retries: int = 3) -> Optional[dict | list]:
    """HTTP GET with 429-aware exponential backoff."""
    for attempt in range(_retries):
        try:
            r = SESSION.get(url, params=params, timeout=TIMEOUT)
            if r.status_code == 429:
                wait = 2 ** attempt
                print(c("amber", f"  ⏳ Rate limited — waiting {wait}s..."), end="\r")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            print(c("red", f"  HTTP error {e.response.status_code} for {url}"))
            return None
        except requests.exceptions.Timeout:
            print(c("red", f"  Timeout fetching {url}"))
            return None
        except Exception as e:
            print(c("red", f"  Error: {e}"))
            return None
    print(c("red", f"  Gave up after {_retries} retries: {url}"))
    return None

# ─── STEP 1: METEORA PAGINATED FETCH ─────────────────────────────────────────
#
# Paginated fetch from all_with_pagination — only confirmed params used:
# limit, page, include_token_mints. sort_key/hide_low_tvl cause HTTP 400.
# All sorting and filtering is done client-side after fetching.
# Each pool object contains fees_24h, fee_tvl_ratio, liquidity, bin_step,
# base_fee_percentage, apr, mint_x/y — no per-token follow-up calls needed.

def _fetch_meteora_page(page: int, page_size: int = 100) -> tuple[list[dict], int]:
    """
    Fetch one page of SOL-paired DLMM pools.
    Only uses confirmed-working params: limit, page, include_token_mints.
    Returns (pairs_list, total_count).
    """
    data = get(
        f"{METEORA_API}/pair/all_with_pagination",
        params={
            "limit":               page_size,
            "page":                page,
            "include_token_mints": SOL_MINT,
        }
    )
    if not data:
        return [], 0
    pairs = data.get("pairs", data) if isinstance(data, dict) else data
    total = int(data.get("total", 0)) if isinstance(data, dict) else 0
    return (pairs if isinstance(pairs, list) else []), total


def fetch_meteora_pools(fetch_limit: int = 500) -> list[dict]:
    """
    Fetch SOL-paired DLMM pools via pagination, running pages concurrently.
    Sorts client-side by fees_24h desc — the API sort_key param is not
    supported and causes 400 errors.
    fetch_limit: approximate max pools to retrieve (rounded up to page boundary).
    """
    PAGE_SIZE    = 100
    MAX_WORKERS  = 4    # concurrent page fetches — Meteora tolerates this fine

    # Page 0 first to learn total count
    print(c("cyan", "📡 Fetching Meteora DLMM pools..."), end=" ", flush=True)
    page0, total = _fetch_meteora_page(0, PAGE_SIZE)
    if not page0:
        print()
        return []

    # How many more pages do we need?
    pages_needed = min(
        (fetch_limit - PAGE_SIZE + PAGE_SIZE - 1) // PAGE_SIZE,   # ceil((limit-100)/100)
        (total - PAGE_SIZE + PAGE_SIZE - 1) // PAGE_SIZE if total else 0
    )
    pages_needed = max(0, pages_needed)

    all_pairs = list(page0)

    if pages_needed > 0:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futs = {pool.submit(_fetch_meteora_page, p, PAGE_SIZE): p
                    for p in range(1, pages_needed + 1)}
            for fut in as_completed(futs):
                pairs, _ = fut.result()
                all_pairs.extend(pairs)

    print(c("gray", f"fetched {len(all_pairs)} pools (API total: {total})"))

    # Sort client-side by fees_24h descending — highest fee pools first
    all_pairs.sort(key=lambda p: float(p.get("fees_24h") or 0), reverse=True)
    return all_pairs


def parse_meteora_pool(pool: dict) -> dict:
    """
    Normalise a raw Meteora pool object into our working dict.
    All the data we need is already here — no follow-up calls.
    """
    def f(*keys, default=0.0):
        for k in keys:
            v = pool.get(k)
            if v is not None:
                try: return float(v)
                except: pass
        return default

    liquidity  = f("liquidity")
    fees_24h   = f("fees_24h")
    fee_tvl_24h = (fees_24h / liquidity * 100) if liquidity > 0 and fees_24h > 0 else 0.0

    # fee_tvl_ratio block: {min_30, hour_1, ..., hour_24}
    ftvl = pool.get("fee_tvl_ratio", {})
    if isinstance(ftvl, dict):
        fee_tvl_24h = float(ftvl.get("hour_24", fee_tvl_24h) or fee_tvl_24h) * 100
        # Normalise if stored as fraction (0.27) not percent (27)
        if 0 < fee_tvl_24h < 2:
            fee_tvl_24h *= 100

    vol_24h = f("trade_volume_24h")

    # Granular fees (useful for freshness check)
    fees_obj = pool.get("fees", {}) or {}
    fees_1h  = float(fees_obj.get("hour_1", 0) or 0)
    fees_6h  = float(fees_obj.get("hour_6", fees_obj.get("hour_12", 0)) or 0) / 2  # approximate

    # Token addresses: mint_x is usually the non-SOL token for SOL pairs
    mint_x = pool.get("mint_x", "")
    mint_y = pool.get("mint_y", "")
    token_addr = mint_x if mint_y == SOL_MINT else (mint_y if mint_x == SOL_MINT else mint_x)

    return {
        "pool_addr":     pool.get("address", ""),
        "name":          pool.get("name", ""),
        "token_addr":    token_addr,
        "mint_x":        mint_x,
        "mint_y":        mint_y,
        "liquidity":     liquidity,
        "fees_24h":      fees_24h,
        "fees_1h":       fees_1h,
        "vol_24h":       vol_24h,
        "fee_tvl_24h":   round(fee_tvl_24h, 4),
        "bin_step":      int(f("bin_step")),
        "base_fee_pct":  f("base_fee_percentage"),
        "max_fee_pct":   f("max_fee_percentage"),
        "apr":           f("apr"),
        "apy":           f("apy"),
        "is_blacklisted": bool(pool.get("is_blacklisted", False)),
        "is_verified":    bool(pool.get("is_verified", False)),
    }


# ─── STEP 2: DEXSCREENER ENRICHMENT (optional, top-N only) ───────────────────
#
# Meteora doesn't have mcap, pair age, or txn counts. We batch-fetch those
# from DexScreener for the top-N candidates only (after in-memory filtering).
# This is 1-2 DexScreener calls, not one per token.

def enrich_with_dexscreener(pools: list[dict]) -> dict[str, dict]:
    """
    Batch fetch DexScreener pair data for a list of parsed Meteora pools.
    Returns a dict keyed by token_addr → dex pair data.
    DexScreener /tokens/v1 accepts up to 30 addresses per call.
    """
    if not pools:
        return {}

    addrs = list({p["token_addr"] for p in pools if p["token_addr"]})
    if not addrs:
        return {}

    print(c("cyan", f"📡 Enriching top {len(addrs)} tokens with DexScreener data..."))
    result: dict[str, dict] = {}

    # Batch into chunks of 28 (safe under the 30-address limit)
    def fetch_chunk(chunk):
        data = get(f"{DEX_API}/tokens/v1/solana/{','.join(chunk)}")
        return data if isinstance(data, list) else []

    chunks = [addrs[i:i+28] for i in range(0, len(addrs), 28)]

    # Parallel chunk fetches — DexScreener is fine with concurrent calls
    with ThreadPoolExecutor(max_workers=min(len(chunks), 4)) as pool:
        futs = [pool.submit(fetch_chunk, ch) for ch in chunks]
        for fut in as_completed(futs):
            for pair in fut.result():
                addr = (pair.get("baseToken") or {}).get("address", "")
                if not addr:
                    continue
                created_ms = pair.get("pairCreatedAt") or 0
                age_days   = round((time.time()*1000 - created_ms) / 86_400_000, 1) if created_ms else None
                txns       = pair.get("txns", {})
                result[addr] = {
                    "symbol":    (pair.get("baseToken") or {}).get("symbol", "?"),
                    "name":      (pair.get("baseToken") or {}).get("name", ""),
                    "mcap":      float(pair.get("marketCap") or 0),
                    "fdv":       float(pair.get("fdv") or 0),
                    "txns_1h":   (txns.get("h1", {}).get("buys",  0) + txns.get("h1", {}).get("sells",  0)),
                    "txns_24h":  (txns.get("h24",{}).get("buys",  0) + txns.get("h24",{}).get("sells",  0)),
                    "ch_24h":    float((pair.get("priceChange") or {}).get("h24", 0)),
                    "ch_6h":     float((pair.get("priceChange") or {}).get("h6",  0)),
                    "age_days":  age_days,
                    "dex_url":   pair.get("url", ""),
                    "liq_dex":   float((pair.get("liquidity") or {}).get("usd", 0)),
                    "vol_dex_24h": float((pair.get("volume") or {}).get("h24", 0)),
                }
    return result


# ─── STEP 3: FILTERING ────────────────────────────────────────────────────────

def apply_filters(pools: list[dict], args: argparse.Namespace) -> list[dict]:
    """
    Pure in-memory filtering — no API calls. Fast.
    pools: list of parsed_meteora_pool dicts.
    """
    out = []
    for p in pools:
        # Hard skip: blacklisted or zero liquidity
        if p["is_blacklisted"]:
            continue
        if p["liquidity"] < args.min_tvl:
            continue
        if p["fees_24h"] < args.min_fees:
            continue
        if p["vol_24h"] < 5_000:
            continue
        # Derive symbol from pool name if available (e.g. "BONK-SOL" → "BONK")
        name_parts = p["name"].split("-")
        symbol = next((s for s in name_parts if s not in ("SOL","USDC","USDT")), name_parts[0])
        if symbol.upper() in SKIP_SYMBOLS:
            continue
        p["_symbol"] = symbol
        out.append(p)
    return out


# ─── STEP 4: SCORING ──────────────────────────────────────────────────────────

def score_pool(met: dict, dex: Optional[dict] = None) -> tuple[int, dict]:
    """Score 0–100 for DLMM fee-farming suitability."""
    bd = {}

    # ── Fee/TVL 24h (30 pts) ─────────────────────────────────────────────────
    ftv = met["fee_tvl_24h"]
    if   ftv >= 5.0:  ftv_pts = 30
    elif ftv >= 3.0:  ftv_pts = 25
    elif ftv >= 2.0:  ftv_pts = 20
    elif ftv >= 1.0:  ftv_pts = 15
    elif ftv >= 0.5:  ftv_pts = 8
    elif ftv >  0.0:  ftv_pts = 3
    else:             ftv_pts = 0
    bd["fee_tvl_pts"] = ftv_pts
    bd["fee_tvl_24h"] = ftv

    # ── Absolute 24h fees (25 pts) ────────────────────────────────────────────
    fees = met["fees_24h"]
    if   fees >= 20_000: f_pts = 25
    elif fees >= 10_000: f_pts = 20
    elif fees >=  5_000: f_pts = 15
    elif fees >=  1_000: f_pts = 10
    elif fees >=    200: f_pts = 5
    else:                f_pts = 2
    bd["fees_pts"]  = f_pts
    bd["fees_24h"]  = fees

    # ── Liquidity depth (20 pts) ──────────────────────────────────────────────
    liq = met["liquidity"]
    if   liq >= 500_000:                    liq_pts = 15   # too big = dilutes your share
    elif liq >= 100_000 and liq < 500_000:  liq_pts = 20
    elif liq >=  50_000:                    liq_pts = 15
    elif liq >=  20_000:                    liq_pts = 8
    else:                                   liq_pts = 3
    bd["liq_pts"] = liq_pts

    # ── Vol/MCap ratio (15 pts) — only if DexScreener data available ──────────
    vm_pts = 7  # neutral default when no mcap data
    vm_val = 0.0
    if dex and dex.get("mcap", 0) > 0:
        vm_val = met["vol_24h"] / dex["mcap"]
        if   vm_val >= 0.5: vm_pts = 15
        elif vm_val >= 0.3: vm_pts = 12
        elif vm_val >= 0.1: vm_pts = 7
        else:               vm_pts = 2
    bd["vol_mcap_pts"] = vm_pts
    bd["vol_mcap"]     = round(vm_val, 3)

    # ── Pair age (10 pts) — only if DexScreener data available ───────────────
    age_pts = 5  # neutral default
    age = dex.get("age_days") if dex else None
    if age is not None:
        if   2 <= age <= 10:  age_pts = 10
        elif 1 <= age <  2:   age_pts = 8
        elif 10 < age <= 21:  age_pts = 6
        elif age <  1:        age_pts = 3
        else:                 age_pts = 2
    bd["age_pts"] = age_pts

    # ── Red-flag deductions ───────────────────────────────────────────────────
    deductions = 0
    flags = []

    # Fees dropping fast: 1h fees << expected (24h/24)
    expected_1h = met["fees_24h"] / 24
    if met["fees_1h"] > 0 and met["fees_1h"] < expected_1h * 0.3:
        deductions += 8
        flags.append("fees declining fast (1h rate << 24h average)")

    if dex:
        ch24 = dex.get("ch_24h", 0)
        if ch24 < -60:
            deductions += 15; flags.append(f"crashed {ch24:.0f}% in 24h")
        elif ch24 < -40:
            deductions += 8;  flags.append(f"down {ch24:.0f}% in 24h")
        if ch24 > 500:
            deductions += 10; flags.append(f"parabolic +{ch24:.0f}% — likely exit incoming")
        if age is not None and age < 0.5:
            deductions += 12; flags.append("pair under 12h old — rug risk")

    bd["deductions"] = deductions
    bd["flags"]      = flags

    total = ftv_pts + f_pts + liq_pts + vm_pts + age_pts - deductions
    return max(0, min(100, total)), bd


# ─── STEP 5: ROI ESTIMATION ───────────────────────────────────────────────────

def estimate_roi(met: dict, investment_usd: float) -> dict:
    """
    Estimate fee earnings across daily / weekly / monthly horizons.
    All figures are (low, high) bounds based on in-range time assumptions.
    """
    pool_tvl = met["liquidity"]
    fees_24h = met["fees_24h"]

    if pool_tvl == 0 or fees_24h == 0:
        return {}

    share      = investment_usd / (pool_tvl + investment_usd)
    daily_base = fees_24h * share

    def bounds(days: int):
        total = daily_base * days
        return round(total * ROI_LOW_FACTOR, 2), round(total * ROI_HIGH_FACTOR, 2)

    d_lo, d_hi = bounds(1)
    w_lo, w_hi = bounds(7)
    m_lo, m_hi = bounds(30)
    apr = round((daily_base * 365 / investment_usd) * 100, 1) if investment_usd else 0

    return {
        "daily_low":   d_lo, "daily_high":  d_hi,
        "weekly_low":  w_lo, "weekly_high": w_hi,
        "monthly_low": m_lo, "monthly_high": m_hi,
        "apr_pct":     apr,
        "pool_share":  round(share * 100, 3),
    }


# ─── FORMATTING ───────────────────────────────────────────────────────────────

def fmt_usd(n: float) -> str:
    if n >= 1e9: return f"${n/1e9:.2f}B"
    if n >= 1e6: return f"${n/1e6:.2f}M"
    if n >= 1e3: return f"${n/1e3:.1f}K"
    return f"${n:.0f}"

def fmt_pct(n: float) -> str:
    return f"+{n:.2f}%" if n >= 0 else f"{n:.2f}%"

def tier_label(score: int) -> str:
    if score >= 70: return c("green", "🔥 HOT")
    if score >= 50: return c("amber", "⚡ WARM")
    return c("red", "⚠  CAUTION")

def score_bar(score: int, width: int = 20) -> str:
    filled = int(score / 100 * width)
    bar    = "█" * filled + "░" * (width - filled)
    col    = "green" if score >= 70 else "amber" if score >= 50 else "red"
    return c(col, bar) + f" {score}/100"

def recommend_strategy(met: dict, dex: Optional[dict]) -> str:
    ch24 = abs(dex.get("ch_24h", 0)) if dex else 0
    bin_step = met.get("bin_step", 100)
    if ch24 > 80:
        return "Bid/Ask — high volatility, capture oscillations"
    elif ch24 < 15:
        return "Curve tight ±10% — stable price, max fee density"
    else:
        return "Spot distribution ±25% — balanced risk/reward"

def build_reasoning(met: dict, dex: Optional[dict], bd: dict) -> str:
    parts = []
    ftv = bd.get("fee_tvl_24h", 0)
    fees = bd.get("fees_24h", 0)
    if ftv >= 1.0:
        parts.append(f"Fee/TVL of {ftv:.2f}%/day (est. APR {ftv*365:.0f}%) is above threshold — healthy fee generation.")
    else:
        parts.append(f"Fee/TVL of {ftv:.2f}%/day is below 1% — fees may not justify IL risk.")

    if fees >= 5000:
        parts.append(f"Pool earned {fmt_usd(fees)} in 24h — substantial absolute fee volume.")
    elif fees > 0:
        parts.append(f"Pool earned {fmt_usd(fees)} in 24h — modest absolute fees.")

    if dex:
        vm = bd.get("vol_mcap", 0)
        if vm > 0:
            parts.append(f"Vol/MCap {vm:.2f}x — {'strong swap demand.' if vm >= 0.3 else 'moderate trading activity.'}")
        age = dex.get("age_days")
        if age is not None:
            if 2 <= age <= 10:
                parts.append(f"Pair age {age}d is in the 2–10 day sweet spot.")
            elif age < 1:
                parts.append(f"Very new pair ({age}d) — validate before entering.")
            elif age > 20:
                parts.append(f"Older pair ({age}d) — confirm volume is still sustained.")
    else:
        parts.append("DexScreener data unavailable — pair age and mcap unknown.")

    flags = bd.get("flags", [])
    if flags:
        parts.append("⚠ " + "; ".join(flags) + ".")

    # Word-wrap at ~62 chars
    text = " ".join(parts)
    words = text.split()
    lines, line = [], []
    for w in words:
        if len(" ".join(line + [w])) > 62:
            lines.append(" ".join(line)); line = [w]
        else:
            line.append(w)
    if line: lines.append(" ".join(line))
    return "\n".join(f"  {c('gray', l)}" for l in lines)



# ─── TELEGRAM OUTPUT ──────────────────────────────────────────────────────────

def _tg_escape(text: str) -> str:
    """Escape special chars for Telegram MarkdownV2."""
    for ch in r"\_*[]()~`>#+-=|{}.!":
        text = text.replace(ch, f"\\{ch}")
    return text


def format_telegram_result(rank: int, met: dict, dex: Optional[dict],
                            score: int, bd: dict, roi: dict,
                            investment: float, period: str = "weekly") -> str:
    """
    Format a single pool result as a Telegram message block.
    Structure:
      - Header line (plain text, emoji tier)
      - Monospace code block with all metrics  ← clickable links won't work inside
      - Plain-text links outside the code block ← clickable
    Returns a single string ready to send/print.
    """
    symbol = (dex or {}).get("symbol") or met.get("_symbol", met["name"].split("-")[0])
    name   = (dex or {}).get("name", "")
    tier   = "🔥 HOT" if score >= 70 else "⚡ WARM" if score >= 50 else "⚠ CAUTION"

    # ── Header (plain text — outside code block) ─────────────────────────────
    header = f"#{rank} {tier} — {symbol}/SOL  [Score: {score}/100]"

    # ── Metrics block (monospace code block) ─────────────────────────────────
    W = 28   # total width of the code block interior

    def row(label: str, val: str, label2: str = "", val2: str = "") -> str:
        """Two-column row: fixed-width left col, optional right col."""
        left  = f"{label:<9}{val:<8}"   # label 9 wide, val 8 wide → 17 chars total
        right = f"{label2:<5}{val2}" if label2 else ""
        return f"{left}  {right}".rstrip() if right else left.rstrip()

    def divider() -> str:
        return "─" * W

    lines = []

    # Pool metrics
    ftv     = met["fee_tvl_24h"]
    est_apr = ftv * 365
    lines.append(row("TVL",     fmt_usd(met["liquidity"]),
                     "Bin",     f"{met['bin_step']}bps"))
    lines.append(row("24h Fees",fmt_usd(met["fees_24h"]),
                     "Base",    f"{met['base_fee_pct']:.2f}%"))
    lines.append(row("Fee/TVL", f"{ftv:.2f}%/d",
                     "APR",     f"~{est_apr:.0f}%"))

    # DexScreener extras
    vm  = bd.get("vol_mcap", 0)
    age = (dex or {}).get("age_days")
    txn = (dex or {}).get("txns_1h")
    ch  = (dex or {}).get("ch_24h")
    if vm:
        lines.append(row("Vol/MCap", f"{vm:.2f}x",
                         "Age",     f"{age}d" if age is not None else "?"))
    if txn is not None:
        ch_str = fmt_pct(ch) if ch is not None else "?"
        lines.append(row("Txns/hr",  str(txn),
                         "Px\u0394",  ch_str))

    lines.append(divider())

    # ROI — always show all three periods, mark the active one with ▶
    if roi:
        inv_str = fmt_usd(investment)
        roi_periods = [
            ("daily",   "Daily  ", roi.get("daily_low",  0), roi.get("daily_high",  0)),
            ("weekly",  "Weekly ", roi.get("weekly_low", 0), roi.get("weekly_high", 0)),
            ("monthly", "Monthly", roi.get("monthly_low",0), roi.get("monthly_high",0)),
        ]
        lines.append(f"ROI on {inv_str}:")
        for key, label, lo, hi in roi_periods:
            marker = "\u25b6" if key == period else " "
            lines.append(f" {marker} {label}  ~{fmt_usd(lo)} \u2013 {fmt_usd(hi)}")
        share_str = f"{roi.get('pool_share', 0)}%"
        lines.append(f"Est. APR: {roi.get('apr_pct', 0)}%  Share: {share_str}")
    else:
        lines.append("ROI data unavailable")
    lines.append(divider())

    # Strategy
    strat = recommend_strategy(met, dex)
    # Shorten strategy label for compact display
    strat_short = strat.split(" —")[0] if " —" in strat else strat[:W]
    lines.append(f"Strategy: {strat_short}")

    # Flags
    flags = bd.get("flags", [])
    for flag in flags:
        lines.append(f"\u26a0 {flag}")

    # Pool name subtitle if available
    if name:
        lines.insert(0, f"{symbol}  {name[:W-len(symbol)-2]}")
        lines.insert(1, divider())

    code_block = "```\n" + "\n".join(lines) + "\n```"

    # ── Links (plain text, outside code block — clickable in Telegram) ────────
    dex_url  = (dex or {}).get("dex_url") or f"https://dexscreener.com/solana/{met['pool_addr']}"
    rug_url  = f"https://rugcheck.xyz/tokens/{met['token_addr']}"
    pool_url = f"https://app.meteora.ag/dlmm/{met['pool_addr']}"
    links = f"📈 {dex_url}\n🛡 {rug_url}\n💧 {pool_url}"

    return f"{header}\n{code_block}\n{links}"


def print_telegram(results: list[dict], args: argparse.Namespace) -> None:
    """Print all results formatted for Telegram, separated by blank lines."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    # Header message
    print(f"🦞 *OpenClaw DLMM Scan* — {now}")
    print(f"Top {len(results)} pools | Investment: {fmt_usd(args.investment)} | ROI: {args.period}\n")

    for i, r in enumerate(results, 1):
        msg = format_telegram_result(
            rank=i,
            met=r["met"], dex=r["dex"],
            score=r["score"], bd=r["bd"], roi=r["roi"],
            investment=args.investment, period=args.period,
        )
        print(msg)
        if i < len(results):
            print()   # blank line separator between results

    print("\n⚠ Not financial advice. Always verify on rugcheck.xyz before entering.")



def print_result(rank: int, met: dict, dex: Optional[dict],
                 score: int, bd: dict, roi: dict,
                 investment: float, period: str = "weekly") -> None:

    symbol  = (dex or {}).get("symbol") or met.get("_symbol", met["name"].split("-")[0])
    name    = (dex or {}).get("name", "")
    sep     = c("gray", "━" * 58)

    print(f"\n{sep}")
    print(f"#{rank}  {tier_label(score)}  │  "
          f"{c('bold', symbol)}/SOL  │  Score: {score_bar(score)}")
    print(sep)

    print(f"  {'Token:':<20} {c('white', '$'+symbol)}  {c('gray', name)}")
    print(f"  {'Meteora Pool:':<20} {c('cyan', met['pool_addr'][:22])}...")

    age = (dex or {}).get("age_days")
    if age is not None:
        age_col = "green" if 2 <= age <= 10 else "amber" if age < 1 else "gray"
        print(f"  {'Pair age:':<20} {c(age_col, str(age)+' days')}")

    # Pool metrics (all from Meteora — no API call needed)
    print()
    print(f"  {'Pool TVL:':<20} {fmt_usd(met['liquidity'])}")
    print(f"  {'24h Volume:':<20} {fmt_usd(met['vol_24h'])}")
    print(f"  {'24h Fees:':<20} {c('green', fmt_usd(met['fees_24h']))}")
    ftv = met["fee_tvl_24h"]
    ftv_col = "green" if ftv >= 1.0 else "amber" if ftv >= 0.5 else "red"
    est_apr = ftv * 365
    print(f"  {'Fee/TVL 24h:':<20} {c(ftv_col, f'{ftv:.2f}%')}  "
          f"{c('gray', f'(est. APR: {est_apr:.0f}%)')}")
    print(f"  {'Bin Step:':<20} {met['bin_step']} bps")
    print(f"  {'Base Fee:':<20} {met['base_fee_pct']:.2f}%")

    # DexScreener extras (if available)
    if dex:
        print()
        if dex.get("mcap"):
            print(f"  {'MCap:':<20} {fmt_usd(dex['mcap'])}")
            vm = bd.get("vol_mcap", 0)
            vm_col = "green" if vm >= 0.3 else "amber" if vm >= 0.1 else "red"
            print(f"  {'Vol/MCap:':<20} {c(vm_col, f'{vm:.2f}x')}")
        if dex.get("txns_1h") is not None:
            txn_col = "green" if dex["txns_1h"] >= 100 else "amber"
            print(f"  {'Txns/hr:':<20} {c(txn_col, str(dex['txns_1h']))}")
        if dex.get("ch_24h") is not None:
            ch = dex["ch_24h"]
            ch_col = "green" if -20 <= ch <= 100 else "amber" if ch < -20 else "red"
            print(f"  {'Price Δ 24h:':<20} {c(ch_col, fmt_pct(ch))}")

    # Strategy
    strat = recommend_strategy(met, dex)
    print()
    print(f"  {'DLMM Strategy:':<20} {c('cyan', strat)}")

    # ROI — all three periods, active one highlighted
    if roi:
        periods = [
            ("daily",   "Daily ROI",   roi.get("daily_low",  0), roi.get("daily_high",  0)),
            ("weekly",  "Weekly ROI",  roi.get("weekly_low", 0), roi.get("weekly_high", 0)),
            ("monthly", "Monthly ROI", roi.get("monthly_low",0), roi.get("monthly_high",0)),
        ]
        print()
        inv_label = c("gray", f"(on {fmt_usd(investment)}):")
        for key, label, lo, hi in periods:
            marker = "▶ " if key == period else "  "
            col    = "green" if key == period else "gray"
            rng    = f"~{fmt_usd(lo)} – {fmt_usd(hi)}"
            print(f"  {marker}{label:<16} {inv_label} {c(col, rng)}")
        apr_str   = f"{roi['apr_pct']}%"
        share_str = f"{roi['pool_share']}%"
        print(f"  {'  Est. APR:':<20} {c('green', apr_str)}")
        print(f"  {'  Your pool share:':<20} {c('gray', share_str)}")
    else:
        print(f"\n  {c('gray', 'ROI estimate unavailable (no fee data)')}")

    # Risk flags
    flags = bd.get("flags", [])
    if flags:
        print()
        for flag in flags:
            print(f"  {c('red', '⚠')} {flag}")

    # Reasoning
    print()
    print(build_reasoning(met, dex, bd))

    # Links
    dex_url  = (dex or {}).get("dex_url") or f"https://dexscreener.com/solana/{met['pool_addr']}"
    rug_url  = f"https://rugcheck.xyz/tokens/{met['token_addr']}"
    pool_url = f"https://app.meteora.ag/dlmm/{met['pool_addr']}"
    print()
    print(f"  {c('cyan', '📈 DexScreener:')} {dex_url}")
    print(f"  {c('cyan', '🛡  Rugcheck:')}   {rug_url}")
    print(f"  {c('cyan', '💧 Meteora:')}    {pool_url}")


# ─── PIPELINE ─────────────────────────────────────────────────────────────────

def run(args: argparse.Namespace) -> None:
    t_start = time.time()
    print(c("bold", "\n🦞 OpenClaw DLMM Meme Scanner"))
    print(c("gray", f"   {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"))
    print(c("gray", f"   Min TVL: {fmt_usd(args.min_tvl)} | Min 24h Fees: {fmt_usd(args.min_fees)} | "
                    f"Investment: {fmt_usd(args.investment)} | ROI: {args.period}\n"))

    # ── 1. Single Meteora bulk fetch ──────────────────────────────────────────
    raw_pools = fetch_meteora_pools(fetch_limit=args.fetch_limit)
    if not raw_pools:
        print(c("red", "\n❌ No pool data from Meteora. Check your internet connection."))
        sys.exit(1)

    # ── 2. Parse ──────────────────────────────────────────────────────────────
    pools = [parse_meteora_pool(p) for p in raw_pools]
    print(c("gray", f"   Parsed {len(pools)} pools"))

    # ── 3. Filter in-memory — no API calls ────────────────────────────────────
    candidates = apply_filters(pools, args)
    print(c("gray", f"   {len(candidates)} pools passed filters"))

    if not candidates:
        print(c("amber", f"\n⚠ No pools passed filters. Try lowering --min-tvl or --min-fees."))
        sys.exit(0)

    # ── 4. Take top-N by fees for DexScreener enrichment ─────────────────────
    candidates.sort(key=lambda p: p["fees_24h"], reverse=True)
    top_candidates = candidates[:args.top_n * 2]  # fetch 2× top-n for headroom

    dex_map = enrich_with_dexscreener(top_candidates) if not args.no_dex else {}

    # ── 5. Score ──────────────────────────────────────────────────────────────
    results = []
    for met in top_candidates:
        dex  = dex_map.get(met["token_addr"])
        sc, bd = score_pool(met, dex)
        roi    = estimate_roi(met, args.investment)
        results.append({"met": met, "dex": dex, "score": sc, "bd": bd, "roi": roi})

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:args.top_n]

    elapsed = time.time() - t_start
    print(c("gray", f"   Scored {len(results)} candidates → showing top {len(top)}  "
                    f"{c('cyan', f'({elapsed:.1f}s total)')}"))

    # ── 6. Output ─────────────────────────────────────────────────────────────
    if args.telegram:
        print_telegram(top, args)
        return

    if args.json:
        out = []
        for r in top:
            m, d = r["met"], r["dex"] or {}
            out.append({
                "symbol":       d.get("symbol", m.get("_symbol", "")),
                "pool_addr":    m["pool_addr"],
                "token_addr":   m["token_addr"],
                "score":        r["score"],
                "tier":         "hot" if r["score"]>=70 else "warm" if r["score"]>=50 else "caution",
                "liquidity":    m["liquidity"],
                "fees_24h":     m["fees_24h"],
                "fee_tvl_24h":  m["fee_tvl_24h"],
                "vol_24h":      m["vol_24h"],
                "bin_step":     m["bin_step"],
                "base_fee_pct": m["base_fee_pct"],
                "mcap":         d.get("mcap", 0),
                "age_days":     d.get("age_days"),
                "txns_1h":      d.get("txns_1h", 0),
                "ch_24h":       d.get("ch_24h", 0),
                "vol_mcap":     r["bd"].get("vol_mcap", 0),
                "roi":          r["roi"],
                "roi_period":   args.period,
                "flags":        r["bd"].get("flags", []),
                "meteora_url":  f"https://app.meteora.ag/dlmm/{m['pool_addr']}",
                "dex_url":      d.get("dex_url", ""),
                "rug_url":      f"https://rugcheck.xyz/tokens/{m['token_addr']}",
            })
        print(json.dumps(out, indent=2))
        return

    print(c("bold", f"\n📊 Top {len(top)} DLMM LP Candidates  "
                    f"{c('gray', '(ranked by fee-farming score)')}"))
    for i, r in enumerate(top, 1):
        print_result(i, r["met"], r["dex"], r["score"], r["bd"],
                     r["roi"], args.investment, args.period)

    print(f"\n{c('gray', '━' * 58)}")
    print(c("gray", "\n⚠  Not financial advice. Always verify on rugcheck.xyz."))
    print(c("gray", "   Impermanent loss can exceed fees on volatile price moves.\n"))


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="OpenClaw DLMM Meme Scanner — single-request architecture",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--min-tvl",      type=float, default=20_000,
                        help="Minimum pool TVL/liquidity in USD")
    parser.add_argument("--min-fees",     type=float, default=100,
                        help="Minimum pool 24h fees in USD")
    parser.add_argument("--top-n",        type=int,   default=10,
                        help="Number of top pools to display")
    parser.add_argument("--investment",   type=float, default=1_000,
                        help="Your LP investment in USD for ROI calculation")
    parser.add_argument("--period",       type=str,   default="weekly",
                        choices=["daily", "weekly", "monthly"],
                        help="ROI period to highlight")
    parser.add_argument("--fetch-limit",  type=int,   default=500,
                        help="Max pools to pull from Meteora (up to 1000)")
    parser.add_argument("--no-dex",       action="store_true",
                        help="Skip DexScreener enrichment (faster, loses mcap/age data)")
    parser.add_argument("--telegram",      action="store_true",
                        help="Output Telegram-formatted messages (code blocks + clickable links)")
    parser.add_argument("--json",         action="store_true",
                        help="Output raw JSON")

    args = parser.parse_args()
    run(args)

if __name__ == "__main__":
    main()
