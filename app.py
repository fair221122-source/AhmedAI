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

    if ob["bullish_ob"] is None and ob["bearish_ob"] is None:
        return {"type": "NONE"}

    signal = {
        "type": "NONE",
        "trend": trend,
        "bos": bos,
        "choch": choch,
        "fvg": fvg
    }

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
        })

    return signal

# -------- تحليل السوق العام من Binance --------
def get_market_tickers():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    data = requests.get(url).json()
    if not isinstance(data, list):
        return pd.DataFrame()
    df = pd.DataFrame(data)
    # نركز على أزواج USDT فقط
    df = df[df["symbol"].str.endswith("USDT")]
    df["priceChangePercent"] = df["priceChangePercent"].astype(float)
    df["quoteVolume"] = df["quoteVolume"].astype(float)
    return df

def market_overview():
    df = get_market_tickers()
    if df.empty:
        return None

    gainers = df.sort_values("priceChangePercent", ascending=False).head(3)
    losers = df.sort_values("priceChangePercent", ascending=True).head(3)
    top_volume = df.sort_values("quoteVolume", ascending=False).head(5)

    avg_change = df["priceChangePercent"].mean()
    if avg_change > 1:
        bias = "السوق يميل للصعود"
    elif avg_change < -1:
        bias = "السوق يميل للهبوط"
    else:
        bias = "السوق متذبذب / محايد"

    return {
        "bias": bias,
        "avg_change": avg_change,
        "gainers": gainers[["symbol", "priceChangePercent"]],
        "losers": losers[["symbol", "priceChangePercent"]],
        "top_volume": top_volume[["symbol", "quoteVolume"]]
    }

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

# نخزن نتائج الفريمات للملخص
frame_results = {}

# صف أول: 5m - 15m - 1h
row1 = st.columns(3)
labels_row1 = ["قصير 5m", "قصير 15m", "متوسط 1h"]

for col, label in zip(row1, labels_row1):
    interval = intervals[label]
    with col:
        st.subheader(label)
        df = get_klines(symbol=symbol, interval=interval)
        if df.empty or len(df) < 20:
            st.error("⚠️ لا توجد بيانات كافية لهذا الفريم.")
            frame_results[label] = {"trend": "no-data", "signal": "NONE"}
            continue

        signal = full_smc_signal(df, balance=balance, risk_percent=risk_percent)
        frame_results[label] = {
            "trend": signal.get("trend", "no-data"),
            "signal": signal.get("type", "NONE")
        }

        st.line_chart(df[["close"]])

        st.markdown(f"**الاتجاه:** {signal.get('trend')}")
        st.markdown(f"**BOS:** {signal.get('bos')}")
        st.markdown(f"**CHOCH:** {signal.get('choch')}")

        if signal["type"] != "NONE":
            st.success(f"إشارة: {signal['type']}")
            st.write(f"دخول: {signal['entry']}")
            st.write(f"وقف خسارة: {signal['stop']}")
            st.write(f"هدف: {signal['target']}")
            st.write(f"حجم الصفقة التقريبي: {signal['size']:.4f}")
        else:
            st.warning("لا توجد إشارة دخول متوافقة مع الشروط حالياً.")

        st.write("عدد FVG المكتشفة:", len(signal.get("fvg", [])))

# صف ثاني: 4h - Summary - Market Analysis
row2 = st.columns(3)
labels_row2 = ["عالي 4h"]

# مربع 4h
with row2[0]:
    label = "عالي 4h"
    interval = intervals[label]
    st.subheader(label)
    df = get_klines(symbol=symbol, interval=interval)
    if df.empty or len(df) < 20:
        st.error("⚠️ لا توجد بيانات كافية لهذا الفريم.")
        frame_results[label] = {"trend": "no-data", "signal": "NONE"}
    else:
        signal = full_smc_signal(df, balance=balance, risk_percent=risk_percent)
        frame_results[label] = {
            "trend": signal.get("trend", "no-data"),
            "signal": signal.get("type", "NONE")
        }

        st.line_chart(df[["close"]])

        st.markdown(f"**الاتجاه:** {signal.get('trend')}")
        st.markdown(f"**BOS:** {signal.get('bos')}")
        st.markdown(f"**CHOCH:** {signal.get('choch')}")

        if signal["type"] != "NONE":
            st.success(f"إشارة: {signal['type']}")
            st.write(f"دخول: {signal['entry']}")
            st.write(f"وقف خسارة: {signal['stop']}")
            st.write(f"هدف: {signal['target']}")
            st.write(f"حجم الصفقة التقريبي: {signal['size']:.4f}")
        else:
            st.warning("لا توجد إشارة دخول متوافقة مع الشروط حالياً.")

        st.write("عدد FVG المكتشفة:", len(signal.get("fvg", [])))

# مربع الملخص Summary
with row2[1]:
    st.subheader("📊 ملخص الفريمات")
    if frame_results:
        for frame, res in frame_results.items():
            st.markdown(f"**{frame}** → اتجاه: {res['trend']} | إشارة: {res['signal']}")
        # اتجاه عام بسيط
        buy_count = sum(1 for r in frame_results.values() if r["signal"] == "BUY")
        sell_count = sum(1 for r in frame_results.values() if r["signal"] == "SELL")
        if buy_count > sell_count and buy_count >= 2:
            st.success("الاتجاه العام يميل للشراء (Confluence BUY).")
        elif sell_count > buy_count and sell_count >= 2:
            st.error("الاتجاه العام يميل للبيع (Confluence SELL).")
        else:
            st.warning("لا يوجد توافق قوي بين الفريمات حالياً.")
    else:
        st.write("لا توجد بيانات كافية لعرض الملخص.")

# مربع تحليل السوق Market Analysis
with row2[2]:
    st.subheader("🌍 تحليل السوق العام")
    analyze = st.button("تحليل السوق الآن")
    if analyze:
        overview = market_overview()
        if overview is None:
            st.error("تعذر جلب بيانات السوق حالياً.")
        else:
            st.markdown(f"**حالة السوق العامة:** {overview['bias']}")
            st.markdown(f"متوسط نسبة التغيير في السوق: {overview['avg_change']:.2f}%")

            st.markdown("### 📈 أقوى 3 عملات صاعدة")
            st.table(overview["gainers"].rename(columns={
                "symbol": "العملة",
                "priceChangePercent": "نسبة التغيير %"
            }))

            st.markdown("### 📉 أقوى 3 عملات هابطة")
            st.table(overview["losers"].rename(columns={
                "symbol": "العملة",
                "priceChangePercent": "نسبة التغيير %"
            }))

            st.markdown("### 💰 أعلى 5 عملات من حيث حجم التداول")
            top_vol = overview["top_volume"].copy()
            top_vol["quoteVolume"] = top_vol["quoteVolume"].round(0)
            st.table(top_vol.rename(columns={
                "symbol": "العملة",
                "quoteVolume": "حجم التداول (تقريبي)"
            }))
    else:
        st.info("اضغط على زر (تحليل السوق الآن) لعرض أنشط العملات واتجاه السوق.")
