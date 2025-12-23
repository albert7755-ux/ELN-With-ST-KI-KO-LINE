import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品戰情室", layout="wide")
st.title("📉 結構型商品 - 歷史均線與關鍵點位分析")
st.markdown("""
此工具支援 **多檔標的** 批量分析。系統將自動下載 **過去 3 年** 股價，
並計算 **月/季/年線**，同時依據您設定的百分比，自動換算並繪製 **KO / KI / Strike** 水平防線。
""")
st.divider()

# --- 2. 側邊欄：參數設定 ---
st.sidebar.header("1️⃣ 輸入標的 (可多檔)")
default_tickers = "2330.TW, NVDA, TSLA"
tickers_input = st.sidebar.text_area("股票代碼 (用逗號分隔)", value=default_tickers, height=100, help="例如: 2330.TW, AAPL, 0050.TW")

st.sidebar.divider()
st.sidebar.header("2️⃣ 設定結構條件 (%)")
st.sidebar.info("系統將以「最新收盤價」作為 100% 基準，自動計算以下價位：")

# 使用數值輸入框讓您精準設定
ko_pct = st.sidebar.number_input("KO (敲出價 %)", value=103.0, step=0.5, format="%.1f")
strike_pct = st.sidebar.number_input("Strike (執行價 %)", value=100.0, step=1.0, format="%.1f")
ki_pct = st.sidebar.number_input("KI (敲入價 %)", value=65.0, step=1.0, format="%.1f")

run_btn = st.sidebar.button("🚀 開始分析", type="primary")

# --- 3. 核心函數 ---

def get_stock_data(ticker):
    """下載3年資料並計算均線"""
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * 3) # 過去三年
        
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if df.empty:
            return None, f"找不到 {ticker}"
            
        df = df.reset_index()
        
        # 處理 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.loc[:, ~df.columns.duplicated()]
        
        if 'Close' not in df.columns:
            return None, "無收盤價資料"

        # 確保格式正確
        df['Date'] = pd.to_datetime(df['Date'])
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df = df.dropna(subset=['Close'])

        # 計算均線 (MA)
        df['MA20_Month'] = df['Close'].rolling(window=20).mean()   # 月線
        df['MA60_Quarter'] = df['Close'].rolling(window=60).mean() # 季線
        df['MA240_Year'] = df['Close'].rolling(window=240).mean()  # 年線
        
        return df, None
    except Exception as e:
        return None, str(e)

def plot_single_view(df, ticker, current_price, level_price, level_name, color, line_style="dash"):
    """繪製單張圖表 (包含股價、三條均線、一條關鍵水平線)"""
    
    fig = go.Figure()

    # 1. 股價走勢 (K線太亂，改用線圖較清晰，或用區域圖)
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['Close'],
        mode='lines', name='股價',
        line=dict(color='gray', width=1.5),
        opacity=0.6
    ))

    # 2. 三條均線 (月/季/年)
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA20_Month'], mode='lines', name='月線 (20MA)', line=dict(color='#3498db', width=1)))
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA60_Quarter'], mode='lines', name='季線 (60MA)', line=dict(color='#f1c40f', width=1)))
    fig.add_trace(go.Scatter(x=df['Date'], y=df['MA240_Year'], mode='lines', name='年線 (240MA)', line=dict(color='#9b59b6', width=1)))

    # 3. 關鍵價位水平線 (User 指定的 KO/KI/Strike)
    fig.add_hline(
        y=level_price,
        line_dash=line_style,
        line_color=color,
        line_width=3,
        annotation_text=f"{level_name}: {level_price:.2f}",
        annotation_position="top left" if level_name == "KO" else "bottom left"
    )

    # 4. 標示最新價格
    fig.add_trace(go.Scatter(
        x=[df['Date'].iloc[-1]], y=[current_price],
        mode='markers+text',
        marker=dict(color='black', size=8),
        text=[f"現價 {current_price:.2f}"],
        textposition="middle right",
        showlegend=False
    ))

    # 設定版面
    y_vals = df['Close'].tolist() + [level_price]
    # 這裡只取最近 1 年的數據來決定 Y 軸範圍，避免 3 年前的價格差異太大導致圖被壓縮
    recent_vals = df['Close'].tail(250).tolist() + [level_price]
    
    fig.update_layout(
        title=f"{ticker} - {level_name} 檢視",
        xaxis_title=None,
        yaxis_title="價格",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis_range=[min(recent_vals)*0.85, max(recent_vals)*1.15], # 動態調整視角
        hovermode="x unified"
    )
    
    return fig

# --- 4. 執行邏輯 ---

if run_btn:
    # 處理輸入的股票代碼
    ticker_list = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]
    
    if not ticker_list:
        st.warning("請輸入至少一檔股票代碼。")
    else:
        for ticker in ticker_list:
            st.markdown(f"### 📌 標的：{ticker}")
            
            with st.spinner(f"正在下載 {ticker} 資料..."):
                df, err = get_stock_data(ticker)
                
            if err:
                st.error(f"無法讀取 {ticker}: {err}")
                continue
                
            # 取得最新價格作為基準 (Base Price)
            try:
                current_price = float(df['Close'].iloc[-1])
            except:
                st.error(f"{ticker} 價格數據異常")
                continue

            # 自動算出絕對價格
            p_ko = current_price * (ko_pct / 100)
            p_st = current_price * (strike_pct / 100)
            p_ki = current_price * (ki_pct / 100)

            # 顯示摘要數據
            c_info1, c_info2, c_info3, c_info4 = st.columns(4)
            c_info1.metric("最新收盤價 (Base)", f"{current_price:.2f}")
            c_info2.metric(f"KO ({ko_pct}%)", f"{p_ko:.2f}", f"距離 {(p_ko-current_price):.2f}")
            c_info3.metric(f"Strike ({strike_pct}%)", f"{p_st:.2f}")
            c_info4.metric(f"KI ({ki_pct}%)", f"{p_ki:.2f}", f"緩衝 {(current_price-p_ki):.2f}", delta_color="inverse")

            # 繪製三張圖 (依照您的要求)
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.caption("🔴 KO 敲出觀察 (上方阻力)")
                fig1 = plot_single_view(df, ticker, current_price, p_ko, "KO", "red", "dash")
                st.plotly_chart(fig1, use_container_width=True)
                
            with col2:
                st.caption("🟠 KI 敲入觀察 (下方支撐)")
                fig2 = plot_single_view(df, ticker, current_price, p_ki, "KI", "orange", "dot")
                st.plotly_chart(fig2, use_container_width=True)
                
            with col3:
                st.caption("🟢 Strike 執行價觀察 (成本/比價)")
                fig3 = plot_single_view(df, ticker, current_price, p_st, "Strike", "green", "solid")
                st.plotly_chart(fig3, use_container_width=True)
            
            st.divider() # 分隔不同股票

else:
    st.info("👆 請在左側輸入股票代碼並設定條件，按下「開始分析」。")
