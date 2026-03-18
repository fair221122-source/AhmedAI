import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
from datetime import datetime

# ==============================
# 1) إعدادات الصفحة والتصميم
# ==============================
st.set_page_config(page_title="Pro SMC Dashboard", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1e2130; padding: 15px; border-radius: 10px; border: 1px solid #31333f; }
    </style>
    """, unsafe_allow_html=True)

# ==============================
# 2) وظائف جلب البيانات (مع Caching)
# ==============================
@st.cache_data(ttl=60)
def get_futures_symbols():
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
    try:
        data = requests.get(url).json()
        return sorted([item["instId"] for item in data.get("data", [])])
    except:
        return ["BTC-USDT-SWAP"]

@st.cache_data(ttl=30)
def get_klines(symbol, interval="15m", limit=300):
    # تحويل التنسيق ليتوافق مع OKX API
    bar_map = {"5m": "5m", "15m": "15m", "1H": "1H", "4H": "4H", "1D": "1D"}
    url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar={bar_map.get(interval, '15m')}&limit={limit}"
    try:
        data = requests.get(url).json()
        if "data" not in data: return pd.DataFrame()
        
        df = pd.DataFrame(data["data"], columns=['time', 'open', 'high', 'low', 'close', 'vol', 'volCcy', 'confirm'])
        df[['open', 'high', 'low', 'close', 'vol']] = df[['open', 'high', 'low', 'close', 'vol']].astype(float)
        df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms')
        return df.sort_values("time").reset_index(drop=True)
    except:
        return pd.DataFrame()

# ==============================
# 3) المحرك التحليلي (SMC Engine)
# ==============================
class SMCAnalyzer:
    @staticmethod
    def detect_fvg(df):
        fvgs = []
        for i in range(2, len(df)):
            # Bullish FVG (Gap between Candle 1 High and Candle 3 Low)
            if df.low.iloc[i] > df.high.iloc[i-2]:
                fvgs.append({"type": "bullish", "top": df.low.iloc[i], "bottom": df.high.iloc[i-2], "index": i-1})
            # Bearish FVG
            elif df.high.iloc[i] < df.low.iloc[i-2]:
                fvgs.append({"type": "bearish", "top": df.low.iloc[i-2], "bottom": df.high.iloc[i], "index": i-1})
        return fvgs

    @staticmethod
    def get_market_structure(df):
        last_close = df.close.iloc[-1]
        ma20 = df.close.rolling(20).mean().iloc[-1]
        if last_close > ma20: return "BULLISH 🟢"
        if last_close < ma20: return "BEARISH 🔴"
        return "RANGING ⚪"

# ==============================
# 4) واجهة المستخدم (Sidebar)
# ==============================
with st.sidebar:
    st.title("🔍 SMC Scanner")
    st.divider()
    all_symbols = get_futures_symbols()
    selected_symbol = st.selectbox("اختر الزوج", all_symbols, index=all_symbols.index("BTC-USDT-SWAP") if "BTC-USDT-SWAP" in all_symbols else 0)
    selected_interval = st.select_slider("الفريم الزمني", options=["5m", "15m", "1H", "4H", "1D"], value="15m")
    
    st.divider()
    risk_cap = st.number_input("رأس المال ($)", value=1000)
    risk_pc = st.slider("المخاطرة لكل صفقة %", 0.5, 5.0, 1.0)

# ==============================
# 5) المعالجة والعرض الرئيسي
# ==============================
df = get_klines(selected_symbol, selected_interval)

if not df.empty:
    analyzer = SMCAnalyzer()
    trend = analyzer.get_market_structure(df)
    fvgs = analyzer.detect_fvg(df)
    
    # حساب مستويات السيولة (أعلى قمة وأقل قاع في آخر 50 شمعة)
    high_liq = df.high.tail(50).max()
    low_liq = df.low.tail(50).min()

    # --- منطقة الإحصائيات ---
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("الزوج", selected_symbol)
    c2.metric("الاتجاه الحالي", trend)
    c3.metric("سيولة علوية", f"{high_liq:.2f}")
    c4.metric("سيولة سفلية", f"{low_liq:.2f}")

    # --- رسم الشارت ---
    fig = go.Figure()

    # الشموع
    fig.add_trace(go.Candlestick(
        x=df.index, open=df.open, high=df.high, low=df.low, close=df.close,
        name="Price", increasing_line_color='#00ff99', decreasing_line_color='#ff3366'
    ))

    # رسم الـ FVGs (آخر 5 فجوات فقط لعدم ازدحام الشارت)
    for fvg in fvgs[-5:]:
        color = "rgba(0, 255, 153, 0.2)" if fvg["type"] == "bullish" else "rgba(255, 51, 102, 0.2)"
        fig.add_shape(type="rect", x0=fvg["index"], x1=len(df), y0=fvg["bottom"], y1=fvg["top"],
                      fillcolor=color, line_width=0, layer="below")

    # إعدادات الشارت
    fig.update_layout(
        height=700,
        template="plotly_dark",
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- منطقة التوصية الذكية ---
    st.subheader("🛠️ خطة التداول المقترحة")
    
    col_entry, col_sl, col_tp, col_size = st.columns(4)
    
    # منطق بسيط للتوصية بناءً على الاتجاه وآخر FVG
    last_fvg = fvgs[-1] if fvgs else None
    
    if last_fvg and trend == "BULLISH 🟢" and last_fvg["type"] == "bullish":
        entry = last_fvg["top"]
        sl = df.low.iloc[last_fvg["index"]-1]
        tp = high_liq
        pos_size = (risk_cap * (risk_pc/100)) / abs(entry - sl)
        
        col_entry.success(f"ENTRY (Buy Limit)\n\n**{entry:.4f}**")
        col_sl.error(f"STOP LOSS\n\n**{sl:.4f}**")
        col_tp.info(f"TARGET\n\n**{tp:.4f}**")
        col_size.warning(f"POSITION SIZE\n\n**{pos_size:.2f} Units**")
    else:
        st.info("انتظر تشكل نموذج SMC واضح (الاتجاه + فجوة FVG متوافقة)")

else:
    st.error("فشل في جلب البيانات من OKX. تأكد من اتصالك بالإنترنت.")

st.divider()
st.caption(f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data provided by OKX API")
