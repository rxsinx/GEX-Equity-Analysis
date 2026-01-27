# 🚀 NIFTY & BANKNIFTY GEX Analyzer
**Professional Gamma Exposure Analysis Tool for Indian Derivatives Market**

![GEX Dashboard](https://img.shields.io/badge/Platform-Streamlit-blue)
![Python](https://img.shields.io/badge/Python-3.9%2B-green)
![NSE](https://img.shields.io/badge/Data-NSE%20India-orange)

## 📊 What is Gamma Exposure (GEX)?
Gamma Exposure measures the rate of change in delta hedging activity by market makers. When dealers are **short gamma**, they must hedge dynamically by **buying when markets go up and selling when markets go down**, amplifying price movements and creating volatility.

### 🎯 Key Features
- **Real-time NIFTY & BANKNIFTY option chain data** scraping
- **Accurate GEX calculations** with proper Indian market parameters
- **Interactive visualizations** with Plotly charts
- **Dealer positioning analysis** (Long/Short Gamma regimes)
- **Gamma Flip identification** - Critical support/resistance levels
- **Multi-expiry analysis** (Weekly & Monthly expiries)
- **Risk metrics dashboard** with PCR, Max Pain, Vanna, Charm

## 🚀 Quick Start

### Prerequisites
- Python 3.9 or higher
- Windows/Mac/Linux with internet access

### Installation
```bash
# 1. Clone the repository
git clone https://github.com/yourusername/gex-analyzer.git
cd gex-analyzer

# 2. Create virtual environment
python -m venv venv

# 3. Activate virtual environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
