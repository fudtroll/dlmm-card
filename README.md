# 🧪 Meteora DLMM Explorer

A high-performance, real-time dashboard to scan and rank **Meteora DLMM** liquidity pools on Solana. This tool filters pools by the **Fees/TVL ratio** (24h) to help yield farmers identify the most efficient capital opportunities.

## 🚀 Features
* **Real-time API Integration:** Fetches live data directly from Meteora’s DLMM dynamic API.
* **Advanced Filtering:** Filter by Minimum TVL, Minimum Pool Age (down to 6 hours), and Market Cap.
* **Smart Token Detection:** Automatically identifies the "main" token in a pair (excluding stables/SOL) to pull accurate market cap data.
* **Interactive UI:** Built with Streamlit for a responsive, lean, and dark-mode compatible experience.
* **Performance Optimized:** Includes data caching to ensure lightning-fast UI responses when adjusting filters.

## 🛠️ Installation

### 1. Clone the Repository
```bash
git clone [https://github.com/YOUR_USERNAME/meteora-dlmm-explorer.git](https://github.com/YOUR_USERNAME/meteora-dlmm-explorer.git)
cd meteora-dlmm-explorer
