import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime, timezone

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Meteora DLMM Explorer",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded"
)

BASE_URL = "https://dlmm.datapi.meteora.ag"
STABLE_OR_NATIVE = ["SOL", "WSOL", "USDC", "USDT", "USDH", "UXD"]

# --- UTILS ---
def parse_created_at(val):
    if val is None: return None
    if isinstance(val, (int, float)):
        if val > 100_000_000_000: val /= 1000.0
        return datetime.fromtimestamp(val, tz=timezone.utc)
    if isinstance(val, str):
        try: return datetime.fromisoformat(val.replace('Z', '+00:00'))
        except: return None
    return None

def fmt_usd(v):
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.2f}M"
    if v >= 1e3: return f"${v/1e3:.1f}K"
    return f"${v:.2f}"

@st.cache_data(ttl=300) # Cache for 5 minutes
def fetch_meteora_pools():
    all_processed = []
    now = datetime.now(timezone.utc)
    page = 1
    limit = 100
    
    # Simple status indicator for data fetching
    with st.spinner("Fetching data from Meteora DLMM..."):
        while True:
            try:
                url = f"{BASE_URL}/pools?page={page}&limit={limit}"
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                payload = resp.json()
                pools = payload.get("data", [])
                if not pools: break
                
                for p in pools:
                    # Data Extraction
                    tvl = float(p.get("tvl", 0) or 0)
                    created_dt = parse_created_at(p.get("created_at"))
                    age_days = (now - created_dt).total_seconds() / 86400 if created_dt else 999
                    
                    config = p.get("pool_config", {})
                    fees_obj = p.get("fees", {})
                    vols_obj = p.get("volume", {})
                    ratio_obj = p.get("fee_tvl_ratio", {})
                    token_x = p.get("token_x", {})
                    token_y = p.get("token_y", {})

                    fees_24h = float(fees_obj.get("24h", 0) or 0)
                    ratio_24h = float(ratio_obj.get("24h", 0) or (fees_24h / tvl * 100 if tvl > 0 else 0))

                    # Market Cap Logic
                    mcap = 0
                    sym_x = token_x.get("symbol", "").upper()
                    sym_y = token_y.get("symbol", "").upper()
                    if sym_x not in STABLE_OR_NATIVE:
                        mcap = float(token_x.get("market_cap", 0) or 0)
                    elif sym_y not in STABLE_OR_NATIVE:
                        mcap = float(token_y.get("market_cap", 0) or 0)

                    all_processed.append({
                        "Name": p.get("name", "Unknown"),
                        "Ratio %": ratio_24h,
                        "TVL": tvl,
                        "24H Vol": float(vols_obj.get("24h", 0) or 0),
                        "24H Fees": fees_24h,
                        "Age (Days)": round(age_days, 2),
                        "Bin Step": config.get("bin_step"),
                        "Fee Tier": f"{config.get('base_fee_pct', 0)}%",
                        "Token Mcap": mcap,
                        "Address": p.get("address")
                    })

                # Pagination break if TVL gets too low (optional, but keeps it fast)
                if float(pools[-1].get("tvl", 0) or 0) < 1000: break
                page += 1
                if page > 20: break # Safety cap
                time.sleep(0.05)
            except Exception:
                break
    return pd.DataFrame(all_processed)

# --- UI LAYOUT ---
st.title("🧪 Meteora DLMM Ranker")
st.markdown("Discover high-yield liquidity pools on Solana by Fees/TVL ratio.")

# Sidebar Controls
with st.sidebar:
    st.header("Filters")
    min_tvl = st.number_input("Min TVL ($)", value=50000, step=10000)
    min_age = st.slider("Min Pool Age (Days)", 0.0, 7.0, 0.25, 0.05)
    top_n = st.number_input("Display Top N", value=25, step=5)
    
    st.divider()
    if st.button("🔄 Refresh Data", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- LOGIC ---
df = fetch_meteora_pools()

if not df.empty:
    # Filter
    filtered_df = df[
        (df["TVL"] >= min_tvl) & 
        (df["Age (Days)"] >= min_age)
    ].sort_values("Ratio %", ascending=False).head(top_n)

    # Metrics Summary
    m1, m2, m3 = st.columns(3)
    m1.metric("Top Yield", f"{filtered_df['Ratio %'].max():.2f}%")
    m2.metric("Avg TVL", fmt_usd(filtered_df['TVL'].mean()))
    m3.metric("Total Pools Found", len(filtered_df))

    # Display Table with Conditional Formatting
    st.dataframe(
        filtered_df,
        column_config={
            "Ratio %": st.column_config.NumberColumn("Fees/TVL (24H)", format="%.3f%%"),
            "TVL": st.column_config.NumberColumn("TVL", format="$%.2f"),
            "24H Vol": st.column_config.NumberColumn("Vol 24H", format="$%.2f"),
            "24H Fees": st.column_config.NumberColumn("Fees 24H", format="$%.2f"),
            "Token Mcap": st.column_config.NumberColumn("Mcap", format="$%.2f"),
            "Address": st.column_config.TextColumn("Pool Address"),
        },
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning("No data found or API issue. Try lowering the TVL filter.")

st.caption("Data provided by Meteora DLMM API. Built with Streamlit.")
