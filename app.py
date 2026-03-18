import streamlit as st
import pandas as pd
import requests
import plotly.graph_objects as go
import time

# ==============================
# 1) إعدادات الطلبات (Headers)
# ==============================
# إضافة Header يجعل الطلب يبدو كأنه من متصفح حقيقي لتجنب الحظر
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# ==============================
# 2) وظائف جلب البيانات المعدلة
# ==============================
@st.cache_data(ttl=60)
def get_futures_symbols():
    url = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        data = response.json()
        if data.get("code") == "0":
            return sorted([item["instId"] for item in data.get("data", [])])
        else:
            st.warning(f"OKX Error: {data.get('msg')}")
            return ["BTC-USDT-SWAP", "ETH-USDT-SWAP"]
    except Exception as e:
        st.error(f"خطأ في الاتصال: {e}")
        return ["BTC-USDT-SWAP"]

@st.cache_data(ttl=30)
def get_klines(symbol, interval="15m", limit=300):
    # تحويل الفريمات لتناسب OKX
    url = f"https://www.okx.com/api/v5/market/candles?instId={symbol}&bar={interval}&limit={limit}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        data = response.json()
        
        if data.get("code") != "0":
            st.error(f"فشل جلب الشموع: {data.get('msg')}")
            return pd.DataFrame()

        # معالجة البيانات
        raw_data = data.get("data", [])
        if not raw_data:
            return pd.DataFrame()

        df = pd.DataFrame(raw_data, columns=['time', 'open', 'high', 'low', 'close', 'vol', 'volCcy', 'confirm'])
        df[['open', 'high', 'low', 'close', 'vol']] = df[['open', 'high', 'low', 'close', 'vol']].astype(float)
        df['time'] = pd.to_datetime(df['time'].astype(int), unit='ms')
        return df.sort_values("time").reset_index(drop=True)
    except Exception as e:
        st.error(f"حدث خطأ أثناء الاتصال بـ OKX: {e}")
        return pd.DataFrame()

# ==============================
# 3) الواجهة التشغيلية
# ==============================
st.title("🚀 OKX SMC Pro Scanner")

# تجربة جلب الرموز
symbols = get_futures_symbols()
selected_symbol = st.selectbox("اختر زوج التداول", symbols)
interval = st.select_slider("الفريم", options=["5m", "15m", "1H", "4H"], value="15m")

if st.button("تحديث البيانات"):
    with st.spinner('جاري جلب البيانات من المخدم...'):
        df = get_klines(selected_symbol, interval)
        
        if not df.empty:
            st.success(f"تم جلب {len(df)} شمعة بنجاح لزوج {selected_symbol}")
            
            # رسم شارت بسيط للتأكد
            fig = go.Figure(data=[go.Candlestick(x=df['time'],
                            open=df['open'], high=df['high'],
                            low=df['low'], close=df['close'])])
            fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error("لم يتم استلام بيانات. قد يكون الـ IP الخاص بك محظوراً من قبل OKX.")
