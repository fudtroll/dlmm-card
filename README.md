# OpenClaw DLMM Scanner

Solana meme coin LP fee-farming scanner. Finds the best Meteora DLMM pools
by real 24h fees, scores them, and shows ROI estimates.

## Deploy to Streamlit Community Cloud (free)

1. Fork or push this repo to your GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub account
4. Select repo → branch → **Main file: `app.py`**
5. Click Deploy — live in ~2 minutes

## Local run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit web UI |
| `scanner.py` | All scan/score/ROI logic (reused by app.py) |
| `requirements.txt` | Python dependencies |
| `.streamlit/config.toml` | Dark theme config |
| `SKILL.md` | OpenClaw agent skill descriptor |

## Features

- **Single Meteora bulk fetch** — 1-2 API calls total, not 20+
- **Live DexScreener enrichment** — mcap, age, txns/hr, price change
- **Card layout** — 1/2/3 column grid, switchable from sidebar
- **Tier filter** — show HOT only, WARM+, or all
- **All 3 ROI periods** — daily, weekly, monthly always visible
- **5-min cache** — filter/investment tweaks don't re-hit the API
- **Telegram output** — `python3 scanner.py --telegram`
