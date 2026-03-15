"""
OpenClaw DLMM Scanner — Streamlit Web App
Deploy free on streamlit.io community cloud.
Reuses scanner.py logic directly — no API rewrite.
"""

import time
import datetime
import streamlit as st

# ── Must be the very first Streamlit call ─────────────────────────────────────
st.set_page_config(
    page_title="OpenClaw DLMM Scanner",
    page_icon="🦞",
    layout="wide",
    initial_sidebar_state="expanded",
)

import scanner  # local scanner.py — all fetch/parse/score logic lives there

# ─── THEME / CUSTOM CSS ───────────────────────────────────────────────────────

st.markdown("""
<style>
/* ── Global ── */
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
    background: #0e0e16;
    border-right: 1px solid rgba(255,255,255,0.07);
}
section[data-testid="stSidebar"] * { color: #c8c8d4 !important; }
section[data-testid="stSidebar"] h2 { color: #fff !important; font-size: 13px !important; letter-spacing: .08em; text-transform: uppercase; }

/* ── Main bg ── */
.stApp { background: #0a0a0f; }
.main .block-container { padding-top: 1.5rem; max-width: 1400px; }

/* ── Card ── */
.pool-card {
    background: #111118;
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 18px 20px 14px;
    margin-bottom: 16px;
    position: relative;
    overflow: hidden;
}
.pool-card::before {
    content: '';
    position: absolute;
    left: 0; top: 0; bottom: 0;
    width: 3px;
    border-radius: 14px 0 0 14px;
}
.card-hot::before   { background: #22c55e; }
.card-warm::before  { background: #f59e0b; }
.card-caution::before { background: #ef4444; }

/* ── Card header ── */
.card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 14px;
}
.card-rank-symbol {
    display: flex;
    align-items: center;
    gap: 10px;
}
.rank { font-size: 13px; color: #64748b; font-weight: 600; }
.symbol { font-size: 22px; font-weight: 800; color: #fff; letter-spacing: -.5px; }
.pool-name { font-size: 12px; color: #64748b; margin-top: 1px; }
.tier-badge {
    font-size: 11px; font-weight: 700; letter-spacing: .08em;
    text-transform: uppercase; border-radius: 6px;
    padding: 3px 10px; font-family: 'Space Mono', monospace;
}
.badge-hot     { background: rgba(34,197,94,.15);  color: #22c55e; border: 1px solid rgba(34,197,94,.3); }
.badge-warm    { background: rgba(245,158,11,.15); color: #f59e0b; border: 1px solid rgba(245,158,11,.3); }
.badge-caution { background: rgba(239,68,68,.15);  color: #ef4444; border: 1px solid rgba(239,68,68,.3); }

/* ── Score bar ── */
.score-row { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.score-label { font-size: 11px; color: #64748b; font-family: 'Space Mono', monospace; white-space: nowrap; }
.score-track { flex: 1; height: 4px; background: rgba(255,255,255,.07); border-radius: 2px; overflow: hidden; }
.score-fill  { height: 100%; border-radius: 2px; }
.score-num   { font-size: 12px; font-weight: 700; font-family: 'Space Mono', monospace; min-width: 36px; text-align: right; }

/* ── Metrics grid ── */
.metrics-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    margin-bottom: 14px;
}
.metric-box {
    background: rgba(0,0,0,.25);
    border-radius: 8px;
    padding: 9px 11px;
}
.metric-label { font-size: 9px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #475569; font-family: 'Space Mono', monospace; margin-bottom: 4px; }
.metric-val   { font-size: 14px; font-weight: 700; font-family: 'Space Mono', monospace; }
.val-good   { color: #22c55e; }
.val-mid    { color: #f59e0b; }
.val-bad    { color: #ef4444; }
.val-neutral{ color: #e2e8f0; }

/* ── ROI table ── */
.roi-section { margin-bottom: 14px; }
.roi-title { font-size: 10px; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; color: #475569; font-family: 'Space Mono', monospace; margin-bottom: 8px; }
.roi-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 5px 0;
    border-bottom: 1px solid rgba(255,255,255,.05);
}
.roi-row:last-child { border-bottom: none; }
.roi-period { font-size: 12px; color: #94a3b8; font-family: 'Space Mono', monospace; display: flex; align-items: center; gap: 6px; }
.roi-active { color: #fff; font-weight: 700; }
.roi-marker { color: #7c3aed; font-size: 10px; }
.roi-range  { font-size: 13px; font-weight: 700; font-family: 'Space Mono', monospace; }
.roi-range-active { color: #22c55e; }
.roi-range-gray   { color: #64748b; }

/* ── Strategy ── */
.strategy-row {
    display: flex; align-items: center; gap: 8px;
    background: rgba(124,58,237,.08);
    border-radius: 8px; padding: 8px 12px;
    margin-bottom: 12px;
}
.strategy-label { font-size: 10px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: #7c3aed; font-family: 'Space Mono', monospace; }
.strategy-val   { font-size: 12px; color: #c4b5fd; }

/* ── Flags ── */
.flag-row { font-size: 11px; color: #fca5a5; margin-bottom: 4px; }

/* ── Links ── */
.links-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.pool-link {
    display: inline-flex; align-items: center; gap: 4px;
    font-size: 11px; font-family: 'Space Mono', monospace;
    background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.1);
    border-radius: 6px; padding: 4px 10px;
    color: #94a3b8; text-decoration: none !important;
    transition: border-color .15s;
}
.pool-link:hover { border-color: rgba(124,58,237,.5); color: #a78bfa; }
.link-dex  { color: #38bdf8 !important; border-color: rgba(56,189,248,.2) !important; }
.link-rug  { color: #4ade80 !important; border-color: rgba(74,222,128,.2) !important; }
.link-met  { color: #a78bfa !important; border-color: rgba(167,139,250,.2) !important; }

/* ── Header ── */
.app-header { display: flex; align-items: center; gap: 14px; margin-bottom: 8px; }
.app-logo   { font-size: 36px; line-height: 1; }
.app-title  { font-size: 26px; font-weight: 800; color: #fff; letter-spacing: -.5px; margin: 0; }
.app-sub    { font-size: 13px; color: #64748b; margin: 0; font-family: 'Space Mono', monospace; }

/* ── Status bar ── */
.status-bar {
    display: flex; align-items: center; gap: 16px;
    background: #111118; border: 1px solid rgba(255,255,255,.07);
    border-radius: 10px; padding: 10px 16px; margin-bottom: 20px;
    font-size: 12px; font-family: 'Space Mono', monospace; color: #64748b;
    flex-wrap: wrap;
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: #22c55e;
              display: inline-block; margin-right: 6px; animation: blink 2s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }
.status-item { display: flex; align-items: center; gap: 4px; }
.status-val  { color: #c8c8d4; font-weight: 700; }

/* ── Warning box ── */
.warn-box {
    background: rgba(239,68,68,.07);
    border: 1px solid rgba(239,68,68,.2);
    border-radius: 8px; padding: 10px 14px;
    font-size: 12px; color: #fca5a5;
    font-family: 'Space Mono', monospace;
    margin-top: 20px;
}

/* ── Divider ── */
.sect-divider { border: none; border-top: 1px solid rgba(255,255,255,.06); margin: 20px 0; }

/* Force Streamlit button style to match theme */
.stButton > button {
    background: linear-gradient(135deg, #7c3aed, #a855f7) !important;
    color: #fff !important; border: none !important;
    border-radius: 8px !important; font-weight: 700 !important;
    padding: 10px 28px !important; width: 100% !important;
    font-size: 14px !important;
}
.stButton > button:hover { opacity: .9; }
</style>
""", unsafe_allow_html=True)


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def fmt_usd(n: float) -> str:
    if n >= 1e9: return f"${n/1e9:.2f}B"
    if n >= 1e6: return f"${n/1e6:.2f}M"
    if n >= 1e3: return f"${n/1e3:.1f}K"
    return f"${n:.0f}"

def score_color(score: int) -> str:
    if score >= 70: return "#22c55e"
    if score >= 50: return "#f59e0b"
    return "#ef4444"

def vm_class(vm: float) -> str:
    return "val-good" if vm >= 0.3 else "val-mid" if vm >= 0.1 else "val-bad"

def fmt_pct(n: float) -> str:
    return f"+{n:.1f}%" if n >= 0 else f"{n:.1f}%"

def ch_class(ch: float) -> str:
    return "val-good" if -20 <= ch <= 100 else "val-mid" if ch < -20 else "val-bad"


# ─── CACHED DATA FETCHING ─────────────────────────────────────────────────────
# TTL=300s — results refresh every 5 minutes automatically

@st.cache_data(ttl=300, show_spinner=False)
def run_scan(fetch_limit: int, min_tvl: float, min_fees: float, skip_dex: bool):
    """
    Fetch + parse + filter + score. Cached for 5 min so UI interactions
    (changing investment amount, period) don't re-hit the APIs.
    """
    raw = scanner.fetch_meteora_pools(fetch_limit=fetch_limit)
    if not raw:
        return [], 0, 0

    pools = [scanner.parse_meteora_pool(p) for p in raw]

    import argparse
    args = argparse.Namespace(min_tvl=min_tvl, min_fees=min_fees)
    candidates = scanner.apply_filters(pools, args)

    candidates.sort(key=lambda p: p["fees_24h"], reverse=True)
    top_candidates = candidates[:40]   # headroom for scoring re-sort

    dex_map = scanner.enrich_with_dexscreener(top_candidates) if not skip_dex else {}

    scored = []
    for met in top_candidates:
        dex     = dex_map.get(met["token_addr"])
        sc, bd  = scanner.score_pool(met, dex)
        scored.append({"met": met, "dex": dex, "score": sc, "bd": bd})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored, len(pools), len(candidates)


# ─── CARD RENDERER ────────────────────────────────────────────────────────────

def render_card(rank: int, r: dict, investment: float, period: str) -> None:
    met   = r["met"]
    dex   = r["dex"] or {}
    score = r["score"]
    bd    = r["bd"]
    roi   = scanner.estimate_roi(met, investment)

    symbol = dex.get("symbol") or met.get("_symbol", met["name"].split("-")[0])
    name   = dex.get("name", met["name"])
    tier   = "hot" if score >= 70 else "warm" if score >= 50 else "caution"

    tier_emoji = {"hot": "🔥 HOT", "warm": "⚡ WARM", "caution": "⚠ CAUTION"}[tier]
    tier_badge_class = f"badge-{tier}"
    card_class = f"card-{tier}"
    sc_col = score_color(score)

    # Pool URLs
    dex_url  = dex.get("dex_url") or f"https://dexscreener.com/solana/{met['pool_addr']}"
    rug_url  = f"https://rugcheck.xyz/tokens/{met['token_addr']}"
    pool_url = f"https://app.meteora.ag/dlmm/{met['pool_addr']}"

    # Metrics
    ftv     = met["fee_tvl_24h"]
    est_apr = ftv * 365
    ftv_cls = "val-good" if ftv >= 1.0 else "val-mid" if ftv >= 0.5 else "val-bad"
    vm      = bd.get("vol_mcap", 0)
    age     = dex.get("age_days")
    txns    = dex.get("txns_1h")
    ch      = dex.get("ch_24h")

    # Age display
    age_str = f"{age}d" if age is not None else "—"
    age_cls = "val-good" if age is not None and 2 <= age <= 10 else "val-mid" if age is not None and age < 1 else "val-neutral"

    # ROI rows
    roi_rows = [
        ("daily",   "Daily",   roi.get("daily_low",  0), roi.get("daily_high",  0)),
        ("weekly",  "Weekly",  roi.get("weekly_low", 0), roi.get("weekly_high", 0)),
        ("monthly", "Monthly", roi.get("monthly_low",0), roi.get("monthly_high",0)),
    ] if roi else []

    # Flags
    flags_html = "".join(
        f'<div class="flag-row">⚠ {f}</div>'
        for f in bd.get("flags", [])
    )

    # Strategy (shortened)
    strat = scanner.recommend_strategy(met, dex or None)
    strat_short = strat.split(" —")[0] if " —" in strat else strat

    # ROI rows HTML
    roi_rows_html = ""
    for key, label, lo, hi in roi_rows:
        active    = key == period
        p_class   = "roi-active" if active else ""
        r_class   = "roi-range-active" if active else "roi-range-gray"
        marker    = '<span class="roi-marker">▶</span>' if active else '<span style="width:14px;display:inline-block"></span>'
        roi_rows_html += f"""
        <div class="roi-row">
          <span class="roi-period {p_class}">{marker} {label}</span>
          <span class="roi-range {r_class}">~{fmt_usd(lo)} – {fmt_usd(hi)}</span>
        </div>"""

    apr_str   = f"{roi.get('apr_pct', 0)}%" if roi else "—"
    share_str = f"{roi.get('pool_share', 0)}%" if roi else "—"

    # Optional DexScreener metrics row
    dex_metrics_html = ""
    if dex:
        mcap = dex.get("mcap", 0)
        if mcap:
            dex_metrics_html += f"""
            <div class="metric-box">
              <div class="metric-label">MCap</div>
              <div class="metric-val val-neutral">{fmt_usd(mcap)}</div>
            </div>
            <div class="metric-box">
              <div class="metric-label">Vol/MCap</div>
              <div class="metric-val {vm_class(vm)}">{vm:.2f}x</div>
            </div>"""
        if txns is not None:
            txn_cls = "val-good" if txns >= 100 else "val-mid"
            dex_metrics_html += f"""
            <div class="metric-box">
              <div class="metric-label">Txns/hr</div>
              <div class="metric-val {txn_cls}">{txns}</div>
            </div>"""
        if ch is not None:
            dex_metrics_html += f"""
            <div class="metric-box">
              <div class="metric-label">Price Δ 24h</div>
              <div class="metric-val {ch_class(ch)}">{fmt_pct(ch)}</div>
            </div>"""
        if age is not None:
            dex_metrics_html += f"""
            <div class="metric-box">
              <div class="metric-label">Pair age</div>
              <div class="metric-val {age_cls}">{age_str}</div>
            </div>"""

    st.markdown(f"""
    <div class="pool-card {card_class}">

      <!-- Header -->
      <div class="card-header">
        <div class="card-rank-symbol">
          <span class="rank">#{rank}</span>
          <div>
            <div class="symbol">{symbol}<span style="color:#475569;font-size:14px;font-weight:400">/SOL</span></div>
            <div class="pool-name">{name}</div>
          </div>
        </div>
        <span class="tier-badge {tier_badge_class}">{tier_emoji}</span>
      </div>

      <!-- Score bar -->
      <div class="score-row">
        <span class="score-label">LP SCORE</span>
        <div class="score-track">
          <div class="score-fill" style="width:{score}%;background:{sc_col}"></div>
        </div>
        <span class="score-num" style="color:{sc_col}">{score}/100</span>
      </div>

      <!-- Core pool metrics -->
      <div class="metrics-grid">
        <div class="metric-box">
          <div class="metric-label">Pool TVL</div>
          <div class="metric-val val-neutral">{fmt_usd(met['liquidity'])}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">24h Volume</div>
          <div class="metric-val val-neutral">{fmt_usd(met['vol_24h'])}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">24h Fees</div>
          <div class="metric-val val-good">{fmt_usd(met['fees_24h'])}</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Fee/TVL 24h</div>
          <div class="metric-val {ftv_cls}">{ftv:.2f}%</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Est. APR</div>
          <div class="metric-val {ftv_cls}">~{est_apr:.0f}%</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Bin Step</div>
          <div class="metric-val val-neutral">{met['bin_step']} bps</div>
        </div>
        {dex_metrics_html}
      </div>

      <!-- ROI section -->
      <div class="roi-section">
        <div class="roi-title">ROI on {fmt_usd(investment)}</div>
        {roi_rows_html}
        <div style="display:flex;gap:20px;margin-top:8px;font-size:11px;font-family:'Space Mono',monospace;color:#475569">
          <span>APR: <span style="color:#94a3b8">{apr_str}</span></span>
          <span>Your share: <span style="color:#94a3b8">{share_str}</span></span>
        </div>
      </div>

      <!-- Strategy -->
      <div class="strategy-row">
        <span class="strategy-label">Strategy</span>
        <span class="strategy-val">{strat_short}</span>
      </div>

      <!-- Flags -->
      {flags_html}

      <!-- Links -->
      <div class="links-row">
        <a class="pool-link link-dex" href="{dex_url}" target="_blank">📈 DexScreener</a>
        <a class="pool-link link-rug" href="{rug_url}" target="_blank">🛡 Rugcheck</a>
        <a class="pool-link link-met" href="{pool_url}" target="_blank">💧 Meteora</a>
      </div>

    </div>
    """, unsafe_allow_html=True)


# ─── SIDEBAR ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🦞 OpenClaw")
    st.markdown("---")

    st.markdown("## Scan Settings")
    fetch_limit = st.select_slider(
        "Pool fetch limit",
        options=[100, 200, 300, 500, 1000],
        value=300,
        help="How many SOL-paired Meteora pools to pull. More = slower but more thorough.",
    )
    min_tvl = st.number_input(
        "Min TVL ($)",
        min_value=1_000, max_value=500_000,
        value=20_000, step=5_000,
    )
    min_fees = st.number_input(
        "Min 24h Fees ($)",
        min_value=10, max_value=50_000,
        value=200, step=50,
    )
    skip_dex = st.toggle(
        "Skip DexScreener enrichment",
        value=False,
        help="Faster scan — loses MCap, age, txn count data.",
    )

    st.markdown("---")
    st.markdown("## Display Settings")
    top_n = st.slider("Top N results", 3, 20, 10)
    investment = st.number_input(
        "Your investment ($)",
        min_value=100, max_value=1_000_000,
        value=1_000, step=100,
    )
    period = st.radio(
        "Highlight ROI period",
        options=["daily", "weekly", "monthly"],
        index=1,
        horizontal=True,
    )
    cols_count = st.radio(
        "Card columns",
        options=[1, 2, 3],
        index=1,
        horizontal=True,
    )

    st.markdown("---")
    scan_btn = st.button("⚡ Scan Now", use_container_width=True)

    st.markdown("---")
    st.markdown(
        "<div style='font-size:10px;color:#475569;font-family:Space Mono,monospace;line-height:1.6'>"
        "Data: Meteora DLMM API + DexScreener<br>"
        "Refreshes every 5 min<br><br>"
        "⚠ Not financial advice.<br>"
        "Always verify on rugcheck.xyz."
        "</div>",
        unsafe_allow_html=True,
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

# App header
st.markdown("""
<div class="app-header">
  <div class="app-logo">🦞</div>
  <div>
    <p class="app-title">OpenClaw DLMM Scanner</p>
    <p class="app-sub">Solana meme coin LP fee-farming · Live Meteora + DexScreener data</p>
  </div>
</div>
""", unsafe_allow_html=True)

# Trigger scan on button press OR first load
if scan_btn or "scan_results" not in st.session_state:
    with st.spinner("📡 Fetching Meteora DLMM pools..."):
        t0 = time.time()
        scored, total_parsed, total_candidates = run_scan(
            fetch_limit=fetch_limit,
            min_tvl=min_tvl,
            min_fees=min_fees,
            skip_dex=skip_dex,
        )
        elapsed = time.time() - t0
    st.session_state["scan_results"]       = scored
    st.session_state["scan_total_parsed"]  = total_parsed
    st.session_state["scan_total_cands"]   = total_candidates
    st.session_state["scan_elapsed"]       = elapsed
    st.session_state["scan_ts"]            = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

results         = st.session_state.get("scan_results", [])
total_parsed    = st.session_state.get("scan_total_parsed", 0)
total_cands     = st.session_state.get("scan_total_cands", 0)
elapsed         = st.session_state.get("scan_elapsed", 0)
scan_ts         = st.session_state.get("scan_ts", "—")

if not results:
    st.error("❌ No pool data returned. Check your internet connection or try raising the fetch limit.")
    st.stop()

# Status bar
top_n_actual = min(top_n, len(results))
st.markdown(f"""
<div class="status-bar">
  <span class="status-item"><span class="status-dot"></span> <span class="status-val">LIVE</span></span>
  <span class="status-item">Scanned: <span class="status-val">{total_parsed}</span> pools</span>
  <span class="status-item">Passed filters: <span class="status-val">{total_cands}</span></span>
  <span class="status-item">Showing: <span class="status-val">top {top_n_actual}</span></span>
  <span class="status-item">Scan time: <span class="status-val">{elapsed:.1f}s</span></span>
  <span class="status-item">Last scan: <span class="status-val">{scan_ts}</span></span>
</div>
""", unsafe_allow_html=True)

# Filter chips — quick tier filter
tier_filter = st.radio(
    "Filter by tier",
    options=["All", "🔥 HOT only", "⚡ WARM+"],
    index=0,
    horizontal=True,
    label_visibility="collapsed",
)

filtered = results
if tier_filter == "🔥 HOT only":
    filtered = [r for r in results if r["score"] >= 70]
elif tier_filter == "⚡ WARM+":
    filtered = [r for r in results if r["score"] >= 50]

display = filtered[:top_n_actual]

if not display:
    st.warning("No pools match the selected tier filter. Try 'All'.")
    st.stop()

# Render cards in columns
if cols_count == 1:
    for i, r in enumerate(display, 1):
        render_card(i, r, investment, period)
else:
    col_lists = [[] for _ in range(cols_count)]
    for i, r in enumerate(display):
        col_lists[i % cols_count].append((i + 1, r))

    cols = st.columns(cols_count, gap="medium")
    for col, items in zip(cols, col_lists):
        with col:
            for rank, r in items:
                render_card(rank, r, investment, period)

st.markdown("""
<div class="warn-box">
  ⚠ Not financial advice. Always verify each token on rugcheck.xyz before entering any position.
  Impermanent loss can exceed fees earned if price moves significantly outside your LP range.
</div>
""", unsafe_allow_html=True)
