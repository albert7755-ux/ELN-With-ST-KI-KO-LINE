import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品關鍵價位分析 (實戰版)", layout="wide")
st.title("📉 結構型商品 - 關鍵價位三視圖 (實戰報價版)")
st.markdown("輸入股票代碼與關鍵價位，系統將調閱歷史走勢並繪製 KO/KI/Strike 防線。")
st.divider()

# --- 2. 側邊欄：輸入資料 ---
st.sidebar.header("1️⃣ 輸入標的")

# 輸入代碼 (預設 NVDA)
ticker = st.sidebar.text_input("輸入股票代碼 (Yahoo Finance 格式)", value="NVDA", help="美股直接打代碼 (如 AAPL)，台股請加 .TW (如 2330.TW)")

# 選擇觀察期間
lookback = st.sidebar.selectbox("歷史回測期間", ["3個月", "6個月", "1年", "Year to Date (今年以來)"], index=2)

# 載入資料按鈕
if st.sidebar.button("🔍 讀取股價", type="primary"):
    st.session_state['data_loaded'] = True
else:
    if 'data_loaded' not in st.session_state:
        st.session_state['data_loaded'] = False

# --- 3. 資料讀取與處理 ---
df = pd.DataFrame()
current_price = 0.0

if st.session_state['data_loaded']:
    try:
        # 設定時間範圍
        end_date = datetime.now()
        if lookback == "3個月": start_date = end_date - timedelta(days=90)
        elif lookback == "6個月": start_date = end_date - timedelta(days=180)
        elif lookback == "1年": start_date = end_date - timedelta(days=365)
        else: start_date = datetime(end_date.year, 1, 1)

        # 下載資料
        with st.spinner(f"正在下載 {ticker} 股價資料..."):
            stock_data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if stock_data.empty:
            st.error(f"找不到代碼 {ticker} 的資料，請檢查拼字或後綴 (如台股需加 .TW)。")
            st.stop()
            
        # 整理資料
        df = stock_data.reset_index()
        # yfinance 新版 columns 可能是 MultiIndex，處理一下
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df[['Date', 'Close']]
        current_price = float(df['Close'].iloc[-1])
        
        st.sidebar.success(f"✅ 成功讀取！最新收盤價: {current_price:.2f}")

    except Exception as e:
        st.error(f"資料讀取錯誤: {e}")
        st.stop()

# --- 4. 側邊欄：設定關鍵價位 (手動輸入) ---
st.sidebar.divider()
st.sidebar.header("2️⃣ 設定結構條件 (直接輸入)")

# 如果有抓到股價，就用現價當預設值，否則用 100
default_price = current_price if current_price > 0 else 100.0

# 使用 number_input 讓使用者精準輸入
strike_price = st.sidebar.number_input("ST (期初價/執行價)", value=default_price, step=1.0, format="%.2f")
ko_price = st.sidebar.number_input("KO (敲出價 - 上方)", value=default_price * 1.05, step=1.0, format="%.2f")
ki_price = st.sidebar.number_input("KI (敲入價 - 下方)", value=default_price * 0.70, step=1.0, format="%.2f")

# 顯示百分比供參考
if strike_price > 0:
    st.sidebar.caption(f"KO 約為期初價的 {(ko_price/strike_price)*100:.1f}%")
    st.sidebar.caption(f"KI 約為期初價的 {(ki_price/strike_price)*100:.1f}%")

# --- 5. 繪圖邏輯 ---

# 通用繪圖函數
def plot_chart(title, line_price, line_color, line_name, show_fill=False, fill_type="none"):
    fig = go.Figure()
    
    # 1. 畫股價走勢
    if not df.empty:
        fig.add_trace(go.Scatter(
            x=df['Date'], y=df['Close'],
            mode='lines', name=ticker,
            line=dict(color='#1f77b4', width=2)
        ))
        # 自動調整 Y 軸範圍，確保線看得到
        all_prices = df['Close'].tolist() + [line_price]
        y_min, y_max = min(all_prices)*0.95, max(all_prices)*1.05
    else:
        # 如果沒資料，畫個空圖
        y_min, y_max = line_price * 0.5, line_price * 1.5

    # 2. 畫關鍵價位虛線
    fig.add_hline(
        y=line_price, 
        line_dash="dash", # 虛線
        line_color=line_color, 
        line_width=2,
        annotation_text=f"{line_name}: {line_price:.2f}", 
        annotation_position="top left" if fill_type == "ko" else "bottom left"
    )

    # 3. (選用) 畫陰影區域
    if show_fill and not df.empty:
        if fill_type == "ko": # 上方陰影
            fig.add_hrect(y0=line_price, y1=y_max, line_width=0, fillcolor=line_color, opacity=0.1, layer="below")
        elif fill_type == "ki": # 下方陰影
            fig.add_hrect(y0=y_min, y1=line_price, line_width=0, fillcolor=line_color, opacity=0.1, layer="below")

    fig.update_layout(
        title=dict(text=title, font=dict(size=18)),
        xaxis_title="日期",
        yaxis_title="價格",
        height=400,
        margin=dict(l=20, r=20, t=40, b=20),
        yaxis_range=[y_min, y_max],
        showlegend=False
    )
    return fig

# --- 6. 畫面佈局 (三欄顯示) ---

if not df.empty:
    c1, c2, c3 = st.columns(3)

    # 圖 1: KO 敲出
    with c1:
        st.subheader("🚀 KO 敲出觀察")
        fig_ko = plot_chart(f"KO 價格: {ko_price}", ko_price, "red", "KO", show_fill=True, fill_type="ko")
        # 標記曾經觸及 KO 的點
        ko_hits = df[df['Close'] >= ko_price]
        if not ko_hits.empty:
            fig_ko.add_trace(go.Scatter(x=ko_hits['Date'], y=ko_hits['Close'], mode='markers', marker=dict(color='red', symbol='star'), name='觸及KO'))
        st.plotly_chart(fig_ko, use_container_width=True)
        
        distance_ko = (ko_price - current_price) / current_price * 100
        if current_price >= ko_price:
            st.success(f"目前價格已高於 KO！(已敲出)")
        else:
            st.info(f"距離 KO 還差 {distance_ko:.2f}%")

    # 圖 2: KI 敲入
    with c2:
        st.subheader("🛡️ KI 敲入觀察")
        fig_ki = plot_chart(f"KI 價格: {ki_price}", ki_price, "orange", "KI", show_fill=True, fill_type="ki")
        # 標記曾經跌破 KI 的點
        ki_hits = df[df['Close'] <= ki_price]
        if not ki_hits.empty:
            fig_ki.add_trace(go.Scatter(x=ki_hits['Date'], y=ki_hits['Close'], mode='markers', marker=dict(color='orange', symbol='x-thin', size=10), name='跌破KI'))
        st.plotly_chart(fig_ki, use_container_width=True)
        
        distance_ki = (current_price - ki_price) / current_price * 100
        if not ki_hits.empty:
            st.error(f"⚠️ 歷史期間內曾跌破 KI (發生敲入)！")
        else:
            st.success(f"期間內未跌破 KI。目前距離 KI 緩衝 {distance_ki:.2f}%")

    # 圖 3: ST 執行價
    with c3:
        st.subheader("⚖️ ST 期初/執行價")
        fig_st = plot_chart(f"ST 價格: {strike_price}", strike_price, "green", "ST")
        st.plotly_chart(fig_st, use_container_width=True)
        
        diff_st = (current_price - strike_price) / strike_price * 100
        color = "green" if diff_st >= 0 else "red"
        st.markdown(f"目前價格 vs ST: <span style='color:{color}'>**{diff_st:+.2f}%**</span>", unsafe_allow_html=True)

else:
    st.info("👈 請在左側輸入股票代碼並點擊「讀取股價」開始分析。")
    # 顯示範例空圖
    st.markdown("### 等待資料輸入中...")
    c1, c2, c3 = st.columns(3)
    with c1: st.image("https://via.placeholder.com/400x300?text=KO+Chart", caption="KO 敲出圖")
    with c2: st.image("https://via.placeholder.com/400x300?text=KI+Chart", caption="KI 敲入圖")
    with c3: st.image("https://via.placeholder.com/400x300?text=Strike+Chart", caption="ST 執行價圖")
