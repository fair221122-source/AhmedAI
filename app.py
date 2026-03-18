import streamlit as st
import pandas as pd
import numpy as np
import requests
import plotly.graph_objects as go

# ==============================
# 1) جلب أزواج Binance Futures
# ==============================
def get_futures_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    data = requests.get(url).json()
    symbols = [s["symbol"] for s in data["symbols"] if s["contractType"] == "PERPETUAL"]
    return symbols

# ==============================
# 2) جلب الشموع من Binance
# ==============================
def get_klines(symbol, interval="5m", limit=50):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()

    if not isinstance(data, list) or len(data) < 10:
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
# 4) واجهة Streamlit — الشريط العلوي
# ==============================

st.set_page_config(page_title="Smart Money Dashboard", layout="wide")

# نستخدم session_state لحفظ الزوج المختار والفريم المختار
if "selected_symbol" not in st.session_state:
    st.session_state.selected_symbol = "BTCUSDT"

if "selected_interval" not in st.session_state:
    st.session_state.selected_interval = "5m"

if "show_market_analysis" not in st.session_state:
    st.session_state.show_market_analysis = False

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

# جلب أزواج Binance Futures
symbols = get_futures_symbols()

# الشريط العلوي
st.markdown("<h3 style='margin-top:0;'>📌 اختر زوج العملات</h3>", unsafe_allow_html=True)

html = "<div class='scroll-container'>"

for sym in symbols:
    cls = "symbol-btn"
    if sym == st.session_state.selected_symbol:
        cls += " symbol-selected"

    html += f"""
        <span class='{cls}' onclick="fetch('/?symbol={sym}')">{sym}</span>
    """

html += "</div>"

st.markdown(html, unsafe_allow_html=True)

# قراءة الضغط على الزوج
query_params = st.experimental_get_query_params()
if "symbol" in query_params:
    st.session_state.selected_symbol = query_params["symbol"][0]
# ==============================
# 5) أزرار الفريمات + جلب الشموع + تشغيل الاستراتيجيات
# ==============================

st.markdown("<br>", unsafe_allow_html=True)
st.markdown("<h3>⏱️ اختر الفريم</h3>", unsafe_allow_html=True)

interval_buttons = {
    "5Min": "5m",
    "15Min": "15m",
    "1H": "1h",
    "4H": "4h"
}

cols = st.columns(len(interval_buttons))

for i, (label, interval) in enumerate(interval_buttons.items()):
    if cols[i].button(label):
        st.session_state.selected_interval = interval
        st.session_state.show_market_analysis = False

# زر تحليل السوق
if st.button("📊 MARKET ANALYSIS"):
    st.session_state.show_market_analysis = True


# ==============================
# 6) جلب الشموع للفريم المختار
# ==============================

symbol = st.session_state.selected_symbol
interval = st.session_state.selected_interval

df = get_klines(symbol, interval)

if df.empty:
    st.error("⚠️ لا توجد بيانات كافية لهذا الزوج أو الفريم.")
    st.stop()

# ==============================
# 7) تشغيل الاستراتيجيات
# ==============================

balance = 1000
risk_percent = 1

signal = full_smc_signal(df, balance=balance, risk_percent=risk_percent)

trend = signal.get("trend")
bos = signal.get("bos")
choch = signal.get("choch")
entry = signal.get("entry")
stop_loss = signal.get("stop")
target = signal.get("target")
# ==============================
# 8) دالة تحليل السوق العام
# ==============================
def market_overview():
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    data = requests.get(url).json()
    if not isinstance(data, list):
        return None

    df = pd.DataFrame(data)
    df = df[df["symbol"].str.endswith("USDT")]

    df["priceChangePercent"] = df["priceChangePercent"].astype(float)
    df["quoteVolume"] = df["quoteVolume"].astype(float)

    gainers = df.sort_values("priceChangePercent", ascending=False).head(5)
    losers = df.sort_values("priceChangePercent", ascending=True).head(5)
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

# ==============================
# 9) واجهة تحليل السوق + زر العودة
# ==============================
if st.session_state.show_market_analysis:
    st.markdown("### 📊 تحليل السوق العام")
    if st.button("⬅️ العودة إلى الشارت"):
        st.session_state.show_market_analysis = False
        st.experimental_rerun()

    overview = market_overview()
    if overview is None:
        st.error("تعذر جلب بيانات السوق حالياً.")
        st.stop()

    st.markdown(f"**حالة السوق العامة:** {overview['bias']}")
    st.markdown(f"متوسط نسبة التغيير في السوق: {overview['avg_change']:.2f}%")

    st.markdown("### 🔥 أنشط 5 عملات صاعدة")
    st.table(overview["gainers"].rename(columns={
        "symbol": "العملة",
        "priceChangePercent": "نسبة التغيير %"
    }))

    st.markdown("### ❄️ أضعف 5 عملات هابطة")
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

    st.stop()

# ==============================
# 10) شارت Plotly + ملصقات الدخول/الوقف/الهدف
# ==============================

st.markdown(f"### 📈 الشارت: {symbol} — الفريم: {interval}")

fig = go.Figure(data=[
    go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price"
    )
])

fig.update_layout(
    xaxis_title="الشموع",
    yaxis_title="السعر",
    template="plotly_dark",
    height=600,
    margin=dict(l=20, r=20, t=40, b=40)
)

# ملصقات + دبابيس (Entry / Stop / Target)
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

# دخول أخضر – وقف أحمر – هدف أزرق
add_level(entry, "lime", "ENTRY")
add_level(stop_loss, "red", "STOP")
add_level(target, "deepskyblue", "TARGET")

fig.update_layout(shapes=shapes, annotations=annotations)

st.plotly_chart(fig, use_container_width=True)

# معلومات نصية تحت الشارت
st.markdown("### 🧠 تفاصيل الاستراتيجية على هذا الفريم")
st.write(f"**الاتجاه العام:** {trend}")
st.write(f"**BOS:** {bos}")
st.write(f"**CHOCH:** {choch}")

if signal["type"] != "NONE":
    st.success(f"إشارة حالية: {signal['type']}")
    st.write(f"سعر الدخول التقريبي: {entry}")
    st.write(f"وقف الخسارة: {stop_loss}")
    st.write(f"الهدف: {target}")
    st.write(f"حجم الصفقة التقريبي: {signal.get('size', 0):.4f}")
else:
    st.warning("لا توجد إشارة دخول متوافقة مع شروط الاستراتيجية حالياً.")
    
