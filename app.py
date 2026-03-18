import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go

# ==============================
# 1) إعدادات الصفحة
# ==============================
st.set_page_config(page_title="OKX SMC Dashboard", layout="wide")

if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "BTC-USDT-SWAP"

if "selected_interval" not in st.session_state:
    st.session_state.selected_interval = None

if "show_chart" not in st.session_state:
    st.session_state.show_chart = False

if "show_market_analysis" not in st.session_state:
    st.session_state.show_market_analysis = False


# ==============================
# 2) جلب أزواج OKX Futures
# ==============================
def get_futures_symbols():
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
    try:
        data = requests.get(url).json()
        if "data" not in data:
            return []
        return [item["instId"] for item in data["data"]]
    except:
        return []


# ==============================
# 3) جلب الشموع من OKX
# ==============================
def get_klines(symbol, interval="5m", limit=200):
    url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar={interval}&limit={limit}"
    try:
        data = requests.get(url).json()
        if "data" not in data:
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
        df = df.sort_values("time", ascending=True).reset_index(drop=True)
        return df.tail(200).reset_index(drop=True)

    except:
        return pd.DataFrame()


# ==============================
# 4) الاستراتيجيات
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
    if df["close"].iloc[-1] > df["high"].iloc[-2]:
        return "BOS_UP"
    if df["close"].iloc[-1] < df["low"].iloc[-2]:
        return "BOS_DOWN"
    return None

def detect_choch(df):
    if len(df) < 6:
        return None
    last = df["close"].iloc[-1]
    prev = df["close"].iloc[-5]
    if last > prev:
        return "CHOCH_UP"
    if last < prev:
        return "CHOCH_DOWN"
    return None

def liquidity_zones(df):
    return {
        "liquidity_above": df["high"].rolling(10).max().iloc[-1],
        "liquidity_below": df["low"].rolling(10).min().iloc[-1]
    }

def order_block(df):
    bearish = df[df["close"] < df["open"]]
    bullish = df[df["close"] > df["open"]]
    if bearish.empty or bullish.empty:
        return {"bullish_ob": None, "bearish_ob": None}
    return {
        "bullish_ob": bearish.iloc[-1]["low"],
        "bearish_ob": bullish.iloc[-1]["high"]
    }

def detect_fvg(df):
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
    dist = abs(entry - stop)
    if dist == 0:
        return 0
    return (balance * (risk_percent / 100)) / dist

def full_smc_signal(df):
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

    if trend == "uptrend" and (bos == "BOS_UP" or choch == "CHOCH_UP"):
        entry = ob["bullish_ob"]
        stop = liq["liquidity_below"]
        size = risk_management(entry, stop)
        signal.update({"type": "BUY", "entry": entry, "stop": stop, "target": liq["liquidity_above"], "size": size})

    elif trend == "downtrend" and (bos == "BOS_DOWN" or choch == "CHOCH_DOWN"):
        entry = ob["bearish_ob"]
        stop = liq["liquidity_above"]
        size = risk_management(entry, stop)
        signal.update({"type": "SELL", "entry": entry, "stop": stop, "target": liq["liquidity_below"], "size": size})

    return signal


# ==============================
# 5) الشريط العلوي
# ==============================
symbols = get_futures_symbols()

st.markdown("### 🔥 اختر الزوج")
cols = st.columns(5)
i = 0
for sym in symbols[:20]:
    if cols[i].button(sym):
        st.session_state.selected_symbol = sym
    i = (i + 1) % 5


# ==============================
# 6) أزرار الفريمات (أفقية)
# ==============================
st.markdown("### ⏱️ اختر الفريم")

c1, c2, c3, c4 = st.columns(4)

if c1.button("5Min"):
    st.session_state.selected_interval = "5m"
    st.session_state.show_chart = True

if c2.button("15Min"):
    st.session_state.selected_interval = "15m"
    st.session_state.show_chart = True

if c3.button("1H"):
    st.session_state.selected_interval = "1H"
    st.session_state.show_chart = True

if c4.button("4H"):
    st.session_state.selected_interval = "4H"
    st.session_state.show_chart = True


# ==============================
# 7) إخفاء الشارت حتى يتم اختيار فريم
# ==============================
if not st.session_state.show_chart:
    st.stop()


# ==============================
# 8) جلب البيانات + الاستراتيجية
# ==============================
symbol = st.session_state.selected_symbol
interval = st.session_state.selected_interval

df = get_klines(symbol, interval)

if df.empty:
    st.error("لا توجد بيانات كافية")
    st.stop()

signal = full_smc_signal(df)


# ==============================
# 9) الشارت + OB + FVG + ENTRY/STOP/TARGET
# ==============================
fig = go.Figure()

fig.add_trace(go.Candlestick(
    x=df.index,
    open=df["open"],
    high=df["high"],
    low=df["low"],
    close=df["close"],
    name="Price"
))

shapes = []

# ---- Order Blocks (A) ----
ob = order_block(df)
if ob["bullish_ob"]:
    shapes.append(dict(
        type="rect",
        x0=df.index[0],
        x1=df.index[-1],
        y0=ob["bullish_ob"],
        y1=ob["bullish_ob"] + (df["high"].max() - df["low"].min()) * 0.01,
        fillcolor="rgba(0,255,0,0.15)",
        line=dict(color="green")
    ))

if ob["bearish_ob"]:
    shapes.append(dict(
        type="rect",
        x0=df.index[0],
        x1=df.index[-1],
        y0=ob["bearish_ob"] - (df["high"].max() - df["low"].min()) * 0.01,
        y1=ob["bearish_ob"],
        fillcolor="rgba(255,0,0,0.15)",
        line=dict(color="red")
    ))

# ---- FVG ----
for fvg_type, low, high in detect_fvg(df):
    color = "rgba(0,150,255,0.2)" if fvg_type == "bullish" else "rgba(255,150,0,0.2)"
    shapes.append(dict(
        type="rect",
        x0=df.index[0],
        x1=df.index[-1],
        y0=low,
        y1=high,
        fillcolor=color,
        line=dict(color=color)
    ))

# ---- ENTRY / STOP / TARGET ----
def add_level(price, color):
    if price:
        shapes.append(dict(
            type="line",
            x0=df.index[0],
            x1=df.index[-1],
            y0=price,
            y1=price,
            line=dict(color=color, width=2, dash="dot")
        ))

add_level(signal.get("entry"), "lime")
add_level(signal.get("stop"), "red")
add_level(signal.get("target"), "cyan")

fig.update_layout(
    template="plotly_dark",
    height=650,
    shapes=shapes
)

st.plotly_chart(fig, use_container_width=True)

st.write("### 🧠 تفاصيل الاستراتيجية")
st.json(signal)
