import streamlit as st
import pandas as pd
import numpy as np
import requests

# -------- جلب الشموع من Binance Public API --------
def get_klines(symbol="BTCUSDT", interval="5m", limit=500):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()

    if not isinstance(data, list) or len(data) < 20:
        return pd.DataFrame()

    df = pd.DataFrame(data, columns=[
        "time","open","high","low","close","volume",
        "close_time","qav","num_trades","taker_base","taker_quote","ignore"
    ])

    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)

    return df

# -------- التحليل --------
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
    # نستخدم نفس منطق الاتجاه لكن نراقب كسر عكسي
    last_high = df["high"].iloc[-2]
    last_low = df["low"].iloc[-2]
    close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-5]

    # إذا كان كان هابط ثم حصل كسر لأعلى → CHOCH_UP
    if close > last_high and close > prev_close:
        return "CHOCH_UP"
    # إذا كان كان صاعد ثم حصل كسر لأسفل → CHOCH_DOWN
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

    if ob["bullish_ob"] is None and ob["bearish_ob"] is None:
        return {"type": "NONE"}

    signal = {"type": "NONE"}

    # BUY: اتجاه صاعد + (BOS_UP أو CHOCH_UP) + Bullish OB
    if trend == "uptrend" and (bos == "BOS_UP" or choch == "CHOCH_UP") and ob["bullish_ob"] is not None:
        entry = ob["bullish_ob"]
        stop = liq["liquidity_below"]
        size = risk_management(entry, stop, balance, risk_percent)
        signal.update({
            "type": "BUY",
            "entry": entry,
            "stop": stop,
            "size": size,
            "target": liq["liquidity_above"],
            "fvg": fvg,
            "bos": bos,
            "choch": choch
        })

    # SELL: اتجاه هابط + (BOS_DOWN أو CHOCH_DOWN) + Bearish OB
    elif trend == "downtrend" and (bos == "BOS_DOWN" or choch == "CHOCH_DOWN") and ob["bearish_ob"] is not None:
        entry = ob["bearish_ob"]
        stop = liq["liquidity_above"]
        size = risk_management(entry, stop, balance, risk_percent)
        signal.update({
            "type": "SELL",
            "entry": entry,
            "stop": stop,
            "size": size,
            "target": liq["liquidity_below"],
            "fvg": fvg,
            "bos": bos,
            "choch": choch
        })

    return signal

# -------- واجهة Streamlit --------
st.set_page_config(page_title="Smart Money Dashboard", layout="wide")
st.title("🧠 Smart Money Concepts – Institutional Dashboard")

symbol = st.sidebar.text_input("الزوج", "BTCUSDT")
balance = st.sidebar.number_input("رصيد الحساب (يدوي)", value=1000.0)
risk_percent = st.sidebar.slider("نسبة المخاطرة لكل صفقة %", 0.1, 5.0, 1.0)

intervals = {
    "قصير 5m": "5m",
    "قصير 15m": "15m",
    "متوسط 1h": "1h",
    "عالي 4h": "4h"
}

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

            if df.empty or len(df) < 20:
                st.error("⚠️ لا توجد بيانات كافية لهذا الفريم.")
                continue

            signal = full_smc_signal(df, balance=balance, risk_percent=risk_percent)

            st.line_chart(df[["close"]])

            st.markdown(f"**الاتجاه:** {market_structure(df)}")
            st.markdown(f"**BOS:** {detect_bos(df)}")
            st.markdown(f"**CHOCH:** {detect_choch(df)}")

            if signal["type"] != "NONE":
                st.success(f"إشارة: {signal['type']}")
                st.write(f"دخول: {signal['entry']}")
                st.write(f"وقف خسارة: {signal['stop']}")
                st.write(f"هدف: {signal['target']}")
                st.write(f"حجم الصفقة التقريبي: {signal['size']:.4f}")
            else:
                st.warning("لا توجد إشارة دخول متوافقة مع الشروط حالياً.")

            st.write("عدد FVG المكتشفة:", len(signal.get("fvg", [])))
