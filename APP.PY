import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 網頁設定 ---
st.set_page_config(page_title="ELN 結構型商品分析", layout="wide")

st.title("🏦 ELN 結構型商品 - 互動式分析儀表板")
st.markdown("輸入股票代號與結構條件，自動生成 **均線分析** 與 **歷史勝率** 報告。")

# --- 2. 側邊欄：輸入參數 ---
with st.sidebar:
    st.header("1️⃣ 設定產品參數")
    ticker = st.text_input("股票代號 (如 NVDA, TSLA, 2330.TW)", "NVDA").upper()
    
    st.header("2️⃣ 設定結構條件")
    # 如果輸入 0，程式稍後會自動抓最新價
    ref_price_input = st.number_input("期初價格 (Ref) [輸入 0 自動抓最新價]", value=0.0)
    
    ko_pct = st.number_input("KO (提前出場) %", value=100.0)
    strike_pct = st.number_input("Strike (履約) %", value=85.0)
    ki_pct = st.number_input("KI (跌破防守) %", value=60.0)
    
    st.markdown("---")
    st.caption("Data Source: Yahoo Finance")

# --- 3. 核心邏輯：抓取資料與計算 ---
@st.cache_data(ttl=3600) # 設定快取，避免重複抓取變慢
def get_data(ticker):
    # 抓取 2 年份資料以計算年線
    start_date = (datetime.now() - timedelta(days=730)).strftime('%Y-%m-%d')
    df = yf.download(ticker, start=start_date, progress=False)
    
    # 處理多層索引 (yfinance 新版修正)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 計算均線
    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()
    df['MA240'] = df['Close'].rolling(window=240).mean()
    return df

try:
    with st.spinner(f"正在分析 {ticker} 的歷史數據..."):
        df = get_data(ticker)

    if df.empty:
        st.error(f"找不到代號 {ticker}，請確認輸入正確 (台股請加 .TW)。")
        st.stop()

    # 取得最新價格與 Ref
    current_price = df['Close'].iloc[-1]
    
    if ref_price_input == 0:
        ref_price = current_price
        ref_msg = "(自動使用最新價)"
    else:
        ref_price = ref_price_input
        ref_msg = "(使用者指定)"

    # 計算結構價格
    ko_price = ref_price * (ko_pct / 100)
    strike_price = ref_price * (strike_pct / 100)
    ki_price = ref_price * (ki_pct / 100)

    # --- 4. 顯示關鍵數據卡片 ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("標的現價", f"${current_price:.2f}", f"Ref: ${ref_price:.2f}")
    col2.metric("KO 價格", f"${ko_price:.2f}", f"{ko_pct}%")
    col3.metric("Strike 價格", f"${strike_price:.2f}", f"{strike_pct}%")
    
    # KI 距離計算
    dist_to_ki = (current_price - ki_price) / current_price * 100
    ki_color = "normal" if dist_to_ki > 10 else "inverse"
    col4.metric("KI 價格", f"${ki_price:.2f}", f"距離 {dist_to_ki:.1f}%", delta_color=ki_color)

    # --- 5. 繪製互動走勢圖 (Plotly) ---
    st.subheader("📈 股價走勢與結構防守線 (含均線)")
    
    fig = go.Figure()

    # K線圖 (或折線圖，這裡用折線比較清楚顯示均線)
    fig.add_trace(go.Scatter(x=df.index, y=df['Close'], mode='lines', name='收盤價', line=dict(color='#1f77b4', width=2)))

    # 均線
    fig.add_trace(go.Scatter(x=df.index, y=df['MA20'], mode='lines', name='月線 (20MA)', line=dict(color='purple', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], mode='lines', name='季線 (60MA)', line=dict(color='green', width=1)))
    fig.add_trace(go.Scatter(x=df.index, y=df['MA240'], mode='lines', name='年線 (240MA)', line=dict(color='brown', width=1)))

    # 結構線 (KO/Strike/KI)
    # 為了不讓圖縮得太小，我們只畫最後 18 個月
    plot_df = df.iloc[-380:] 
    
    fig.add_hline(y=ko_price, line_dash="solid", line_color="red", annotation_text=f"KO ${ko_price:.1f}", annotation_position="top right")
    fig.add_hline(y=strike_price, line_dash="dash", line_color="green", annotation_text=f"Strike ${strike_price:.1f}", annotation_position="bottom right")
    fig.add_hline(y=ki_price, line_dash="dash", line_color="orange", annotation_text=f"KI ${ki_price:.1f}", annotation_position="bottom right")

    # 設定圖表版面
    fig.update_layout(
        height=600,
        hovermode="x unified",
        xaxis_title="日期",
        yaxis_title="價格",
        legend=dict(orientation="h", y=1.02, x=0, xanchor="left", yanchor="bottom")
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- 6. 歷史勝率分析 (您想要的勝率圖) ---
    st.subheader("📊 歷史持有勝率分析 (Backtest)")
    st.markdown("計算過去 2 年內，若在任意時間點買進並持有特定天期，獲得**正報酬**的機率。")

    # 計算勝率函數
    periods = {
        '1 個月': 21,
        '3 個月': 63,
        '6 個月 (半強)': 126,
        '1 年': 252
    }
    
    win_data = []
    
    for label, days in periods.items():
        # 計算報酬率: (今天股價 / N天前股價) - 1
        returns = df['Close'].pct_change(periods=days)
        # 移除空的資料
        valid_returns = returns.dropna()
        if len(valid_returns) > 0:
            win_rate = (valid_returns > 0).mean() * 100
        else:
            win_rate = 0
        win_data.append({"持有期間": label, "勝率": win_rate})
    
    win_df = pd.DataFrame(win_data)

    # 畫長條圖
    bar_fig = go.Figure(go.Bar(
        x=win_df['持有期間'],
        y=win_df['勝率'],
        text=win_df['勝率'].apply(lambda x: f"{x:.1f}%"),
        textposition='auto',
        marker_color=['#a5d6a7', '#66bb6a', '#43a047', '#1b5e20'] # 漸層綠
    ))
    
    bar_fig.update_layout(
        height=400,
        yaxis=dict(range=[0, 110], title="正報酬機率 (%)"),
        title=f"持有 {ticker} 的歷史勝率"
    )
    st.plotly_chart(bar_fig, use_container_width=True)

except Exception as e:
    st.error(f"發生錯誤: {e}")
