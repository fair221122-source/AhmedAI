import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go

# ==============================
# 1) جلب أزواج OKX Futures (SWAP)
# ==============================
def get_futures_symbols():
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
    try:
        data = requests.get(url).json()

        if "data" not in data:
            st.warning("⚠️ تعذر جلب أزواج OKX Futures.")
            return []

        symbols = [item["instId"] for item in data["data"]]
        return symbols

    except Exception:
        st.error("⚠️ خطأ أثناء الاتصال بـ OKX.")
        return []


# ==============================
# 2) جلب الشموع من OKX
# ==============================
def get_klines(symbol, interval="5m", limit=50):
    url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar={interval}&limit={limit}"
    try:
        data = requests.get(url).json()

        if "data" not in data or len(data["data"]) == 0:
            return pd.DataFrame()

        rows = []
        for c in data["data"]:
            rows.append({
                "time": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5])
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("time")
        df.reset_index(drop=True, inplace=True)
        return df

    except Exception:
        return pd.DataFrame()


# ==============================
# 3) الاستراتيجيات (كما هي)
# ==============================
def market_structure(df):
    if len(df) < 6:
        return "no-data"
    last = df["close"].iloc[-1]
    prev = df["close"].iloc[-5]
    if last > prev:
        return "uptrend"
    elif last < prev:
        return "downtrend"
    return "sideways"

def detect_bos(df):
    if len(df) < 3:
        return None
    last_high = df["high"].iloc[-2]
    last_low = df["low"].iloc[-2]
    close = df["close"].iloc[-1]
    if close > last_high:
        return "BOS_UP"
    if close < last_low:
        return "BOS_DOWN"
    return None

def detect_choch(df):
    if len(df) < 6:
        return None
    last_high = df["high"].iloc[-2]
    last_low = df["low"].iloc[-2]
    close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-5]

    if close > last_high and close > prev_close:
        return "CHOCH_UP"
    if close < last_low and close < prev_close:
        return "CHOCH_DOWN"
    return None

def liquidity_zones(df):
    if len(df) < 20:
        return {"liquidity_above": None, "liquidity_below": None}
    return {
        "liquidity_above": df["high"].rolling(10).max().iloc[-1],
        "liquidity_below": df["low"].rolling(10).min().iloc[-1]
    }

def order_block(df):
    if len(df) < 10:
        return {"bullish_ob": None, "bearish_ob": None}
    bearish = df[df["close"] < df["open"]]
    bullish = df[df["close"] > df["open"]]
    if bearish.empty or bullish.empty:
        return {"bullish_ob": None, "bearish_ob": None}
    return {
        "bullish_ob": bearish.iloc[-1]["low"],
        "bearish_ob": bullish.iloc[-1]["high"]
    }

def detect_fvg(df):
    if len(df) < 3:
        return []
    fvg_list = []
    for i in range(2, len(df)):
        prev_low = df["low"].iloc[i-2]
        prev_high = df["high"].iloc[i-2]
        curr_low = df["low"].iloc[i]
        curr_high = df["high"].iloc[i]
        if curr_low > prev_high:
            fvg_list.append(("bullish", prev_high, curr_low))
        if curr_high < prev_low:
            fvg_list.append(("bearish", curr_high, prev_low))
    return fvg_list

def risk_management(entry, stop, balance=1000, risk_percent=1):
    if entry is None or stop is None:
        return 0
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        return 0
    return (balance * (risk_percent / 100)) / stop_distance

def full_smc_signal(df, balance=1000, risk_percent=1):
    if len(df) < 20:
        return {"type": "NONE"}

    trend = market_structure(df)
    bos = detect_bos(df)
    choch = detect_choch(df)
    liq = liquidity_zones(df)
    ob = order_block(df)
    fvg = detect_fvg(df)

    signal = {
        "type": "NONE",
        "trend": trend,
        "bos": bos,
        "choch": choch,
        "fvg": fvg
    }

    if trend == "uptrend" and (bos == "BOS_UP" or choch == "CHOCH_UP") and ob["bullish_ob"]:
        entry = ob["bullish_ob"]
        stop = liq["liquidity_below"]
        size = risk_management(entry, stop, balance, risk_percent)
        signal.update({
            "type": "BUY",
            "entry": entry,
            "stop": stop,
            "target": liq["liquidity_above"],
            "size": size
        })

    elif trend == "downtrend" and (bos == "BOS_DOWN" or choch == "CHOCH_DOWN") and ob["bearish_ob"]:
        entry = ob["bearish_ob"]
        stop = liq["liquidity_above"]
        size = risk_management(entry, stop, balance, risk_percent)
        signal.update({
            "type": "SELL",
            "entry": entry,
            "stop": stop,
            "target": liq["liquidity_below"],
            "size": size
        })

    return signal


# ==============================
# 4) واجهة Streamlit
# ==============================
st.set_page_config(page_title="OKX Smart Money Dashboard", layout="wide")

if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "BTC-USDT-SWAP"

if "selected_interval" not in st.session_state:
    st.session_state.selected_interval = "5m"

if "show_market_analysis" not in st.session_state:
    st.session_state.show_market_analysis = False


# ==============================
# 5) الشريط العلوي
# ==============================
st.markdown("""
<style>
.scroll-container {
    width: 100%;
    overflow-x: scroll;
    white-space: nowrap;
    padding: 10px;
    border-bottom: 1px solid #444;
}
.symbol-btn {
    display: inline-block;
    padding: 8px 14px;
    margin-right: 8px;
    background: #222;
    color: white;
    border-radius: 6px;
    cursor: pointer;
    border: 1px solid #555;
    font-size: 15px;
}
.symbol-btn:hover {
    background: #333;
}
.symbol-selected {
    background: #0a84ff !important;
    border-color: #0a84ff !important;
}
</style>
""", unsafe_allow_html=True)

symbols = get_futures_symbols()

html = "<div class='scroll-container'>"
for sym in symbols:
    cls = "symbol-btn"
    if sym == st.session_state.selected_symbol:
        cls += " symbol-selected"
    html += f"<span class='{cls}' onclick=\"fetch('/?symbol={sym}')\">{sym}</span>"
html += "</div>"

st.markdown(html, unsafe_allow_html=True)

query_params = st.experimental_get_query_params()
if "symbol" in query_params:
    st.session_state.selected_symbol = query_params["symbol"][0]


# ==============================
# 6) أزرار الفريمات
# ==============================
st.markdown("<h3>⏱️ اختر الفريم</h3>", unsafe_allow_html=True)

interval_buttons = {
    "5Min": "5m",
    "15Min": "15m",
    "1H": "1H",
    "4H": "4H"
}

cols = st.columns(len(interval_buttons))

for i, (label, interval) in enumerate(interval_buttons.items()):
    if cols[i].button(label):
        st.session_state.selected_interval = interval
        st.session_state.show_market_analysis = False

if st.button("📊 MARKET ANALYSIS"):
    st.session_state.show_market_analysis = True


# ==============================
# 7) تحليل السوق
# ==============================
def market_overview_okx():
    url = "https://www.okx.com/api/v5/market/tickers?instType=SWAP"
    data = requests.get(url).json()

    if "data" not in data:
        return None

    df = pd.DataFrame(data["data"])
    df["change"] = df["last"].astype(float) - df["open24h"].astype(float)
    df["percent"] = (df["change"] / df["open24h"].astype(float)) * 100
    df["vol"] = df["volCcy24h"].astype(float)

    gainers = df.sort_values("percent", ascending=False).head(5)
    losers = df.sort_values("percent", ascending=True).head(5)
    top_volume = df.sort_values("vol", ascending=False).head(5)

    avg_change = df["percent"].mean()
    if avg_change > 1:
        bias = "السوق يميل للصعود"
    elif avg_change < -1:
        bias = "السوق يميل للهبوط"
    else:
        bias = "السوق متذبذب"

    return {
        "bias": bias,
        "gainers": gainers[["instId", "percent"]],
        "losers": losers[["instId", "percent"]],
        "top_volume": top_volume[["instId", "vol"]]
    }

if st.session_state.show_market_analysis:
    st.markdown("### 📊 تحليل السوق العام")
    if st.button("⬅️ العودة"):
        st.session_state.show_market_analysis = False
        st.experimental_rerun()

    overview = market_overview_okx()
    if overview:
        st.write("حالة السوق:", overview["bias"])
        st.write("### 🔥 أعلى 5 صاعدين")
        st.table(overview["gainers"])
        st.write("### ❄️ أعلى 5 هابطين")
        st.table(overview["losers"])
        st.write("### 💰 أعلى 5 حجم تداول")
        st.table(overview["top_volume"])

    st.stop()


# ==============================
# 8) جلب الشموع + الاستراتيجية
# ==============================
symbol = st.session_state.selected_symbol
interval = st.session_state.selected_interval

df = get_klines(symbol, interval)

if df.empty:
    st.error("لا توجد بيانات كافية.")
    st.stop()

signal = full_smc_signal(df)


# ==============================
# 9) الشارت + الملصقات
# ==============================
st.markdown(f"### 📈 الشارت: {symbol} — الفريم: {interval}")

fig = go.Figure(data=[
    go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"]
    )
])

fig.update_layout(
    template="plotly_dark",
    height=600,
    margin=dict(l=20, r=20, t=40, b=40)
)

shapes = []
annotations = []

def add_level(price, color, text):
    if price is None:
        return
    shapes.append(dict(
        type="line",
        x0=df.index[0],
        x1=df.index[-1],
        y0=price,
        y1=price,
        line=dict(color=color, width=1.5, dash="dot")
    ))
    annotations.append(dict(
        x=df.index[-1],
        y=price,
        xanchor="left",
        showarrow=True,
        arrowhead=1,
        arrowsize=1,
        arrowwidth=1,
        arrowcolor=color,
        bgcolor="rgba(0,0,0,0.6)",
        bordercolor=color,
        borderwidth=1,
        text=text,
        font=dict(color="white", size=11)
    ))

add_level(signal.get("entry"), "lime", "ENTRY")
add_level(signal.get("stop"), "red", "STOP")
add_level(signal.get("target"), "deepskyblue", "TARGET")

fig.update_layout(shapes=shapes, annotations=annotations)

st.plotly_chart(fig, use_container_width=True)

st.write("### 🧠 تفاصيل الاستراتيجية")
st.write(signal)
