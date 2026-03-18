import streamlit as st
from binance.client import Client
import pandas as pd
import numpy as np

# -------- إعداد Binance Futures --------
api_key = st.secrets["BINANCE_API_KEY"]
api_secret = st.secrets["BINANCE_API_SECRET"]

client = Client(api_key, api_secret)

# -------- جلب الشموع --------
def get_klines(symbol="BTCUSDT", interval="5m", limit=500):
    data = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","num_trades","taker_base","taker_quote","ignore"
    ])
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    return df

# -------- جلب الرصيد الحقيقي --------
def get_futures_balance():
    balances = client.futures_account_balance()
    for asset in balances:
        if asset["asset"] == "USDT":
            return float(asset["balance"])
    return 0.0

# -------- التحليل --------
def market_structure(df):
    if df["close"].iloc[-1] > df["close"].iloc[-5]:
        return "uptrend"
    elif df["close"].iloc[-1] < df["close"].iloc[-5]:
        return "downtrend"
    else:
        return "sideways"

def detect_bos(df):
    last_high = df["high"].iloc[-2]
    last_low = df["low"].iloc[-2]
    close = df["close"].iloc[-1]

    if close > last_high:
        return "BOS_UP"
    elif close < last_low:
        return "BOS_DOWN"
    else:
        return None

def liquidity_zones(df):
    highs = df["high"].rolling(10).max()
    lows = df["low"].rolling(10).min()
    return {
        "liquidity_above": highs.iloc[-1],
        "liquidity_below": lows.iloc[-1]
    }

def order_block(df):
    last_bearish = df[df["close"] < df["open"]].iloc[-1]
    last_bullish = df[df["close"] > df["open"]].iloc[-1]
    return {
        "bullish_ob": last_bearish["low"],
        "bearish_ob": last_bullish["high"]
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
    risk_amount = balance * (risk_percent / 100)
    stop_distance = abs(entry - stop)
    if stop_distance == 0:
        return 0
    position_size = risk_amount / stop_distance
    return position_size

def full_smc_signal(df, balance=1000, risk_percent=1):
    trend = market_structure(df)
    bos = detect_bos(df)
    liq = liquidity_zones(df)
    ob = order_block(df)
    fvg = detect_fvg(df)

    signal = {"type": "NONE"}

    if trend == "uptrend" and bos == "BOS_UP":
        entry = ob["bullish_ob"]
        stop = liq["liquidity_below"]
        size = risk_management(entry, stop, balance, risk_percent)
        signal.update({
            "type": "BUY",
            "entry": entry,
            "stop": stop,
            "size": size,
            "target": liq["liquidity_above"],
            "fvg": fvg
        })

    elif trend == "downtrend" and bos == "BOS_DOWN":
        entry = ob["bearish_ob"]
        stop = liq["liquidity_above"]
        size = risk_management(entry, stop, balance, risk_percent)
        signal.update({
            "type": "SELL",
            "entry": entry,
            "stop": stop,
            "size": size,
            "target": liq["liquidity_below"],
            "fvg": fvg
        })

    return signal

# -------- واجهة Streamlit --------
st.set_page_config(page_title="Smart Money Dashboard", layout="wide")

st.title("🧠 Smart Money Concepts – Institutional Dashboard")

# عرض الرصيد الحقيقي
real_balance = get_futures_balance()
st.info(f"💰 رصيد العقود الآجلة الحقيقي: {real_balance} USDT")

symbol = st.sidebar.text_input("الزوج", "BTCUSDT")
balance = st.sidebar.number_input("رصيد الحساب (افتراضي)", value=real_balance)
risk_percent = st.sidebar.slider("نسبة المخاطرة لكل صفقة %", 0.1, 5.0, 1.0)

# إضافة فريم 4h
intervals = {
    "قصير 5m": "5m",
    "قصير 15m": "15m",
    "متوسط 1h": "1h",
    "عالي 4h": "4h"
}

# ترتيب الواجهة صفين × عمودين
rows = [
    ["قصير 5m", "قصير 15m"],
    ["متوسط 1h", "عالي 4h"]
]

for row in rows:
    cols = st.columns(2)
    for i, label in enumerate(row):
        interval = intervals[label]
        with cols[i]:
            st.subheader(label)
            df = get_klines(symbol=symbol, interval=interval)
            signal = full_smc_signal(df, balance=balance, risk_percent=risk_percent)

            st.line_chart(df[["close"]])

            st.markdown(f"**الاتجاه:** {market_structure(df)}")
            st.markdown(f"**BOS:** {detect_bos(df)}")

            if signal["type"] != "NONE":
                st.success(f"إشارة: {signal['type']}")
                st.write(f"دخول: {signal['entry']}")
                st.write(f"وقف خسارة: {signal['stop']}")
                st.write(f"هدف: {signal['target']}")
                st.write(f"حجم الصفقة التقريبي: {signal['size']:.4f}")
            else:
                st.warning("لا توجد إشارة واضحة حالياً.")

            st.write("عدد FVG المكتشفة:", len(signal.get("fvg", [])))
