import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品戰情室 (V4.0)", layout="wide")
st.title("📊 結構型商品 - 關鍵點位與歷史風險回測")
st.markdown("""
整合 **技術分析** 與 **歷史統計**：
1. **整合圖表**：在一張圖上同時呈現股價、均線與 KO/KI/Strike 位置。
2. **風險回測**：利用過去 10 年數據，模擬若在歷史上任一天進場，發生 **「跌破 KI」** 或 **「正報酬」** 的機率。
""")
st.divider()

# --- 2. 側邊欄：參數設定 ---
st.sidebar.header("1️⃣ 輸入標的")
default_tickers = "NVDA, TSLA, 2330.TW"
tickers_input = st.sidebar.text_area("股票代碼 (逗號分隔)", value=default_tickers, height=80)

st.sidebar.divider()
st.sidebar.header("2️⃣ 結構條件 (%)")
st.sidebar.info("以「最新收盤價」為 100% 基準：")
ko_pct = st.sidebar.number_input("KO (敲出價 %)", value=103.0, step=0.5, format="%.1f")
strike_pct = st.sidebar.number_input("Strike (執行價 %)", value=100.0, step=1.0, format="%.1f")
ki_pct = st.sidebar.number_input("KI (敲入價 %)", value=65.0, step=1.0, format="%.1f")

st.sidebar.divider()
st.sidebar.header("3️⃣ 回測參數設定")
st.sidebar.caption("設定產品的預計存續期間，用於計算歷史機率：")
period_months = st.sidebar.number_input("產品/觀察天期 (月)", min_value=1, max_value=60, value=6, step=1, help="例如 FCN 通常為 6 或 12 個月")

run_btn = st.sidebar.button("🚀 開始分析", type="primary")

# --- 3. 核心函數 ---

def get_stock_data_10y(ticker):
    """下載過去 10 年資料"""
    try:
        # 下載 10 年資料以進行回測
        df = yf.download(ticker, period="10y", progress=False)
        
        if df.empty:
            return None, f"找不到 {ticker}"
            
        df = df.reset_index()
        
        # 處理 MultiIndex
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df = df.loc[:, ~df.columns.duplicated()]
        
        if 'Close' not in df.columns:
            return None, "無收盤價資料"

        df['Date'] = pd.to_datetime(df['Date'])
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df = df.dropna(subset=['Close'])

        # 計算均線 (僅用於繪圖)
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA240'] = df['Close'].rolling(window=240).mean()
        
        return df, None
    except Exception as e:
        return None, str(e)

def run_backtest(df, ki_percent, months):
    """
    執行歷史回測：
    1. 正報酬機率：持有 N 個月後，報酬率 > 0 的機率。
    2. KI 跌破率：持有 N 個月期間，最低價 < 進場價 * KI% 的機率。
    """
    # 假設一個月 21 個交易日
    trading_days = int(months * 21)
    
    # 建立回測資料
    backtest_df = df[['Date', 'Close']].copy()
    
    # 1. 計算持有 N 個月後的報酬
    # shift(-trading_days) 代表往未來推 N 個月
    backtest_df['Future_Price'] = backtest_df['Close'].shift(-trading_days)
    backtest_df['Return'] = (backtest_df['Future_Price'] - backtest_df['Close']) / backtest_df['Close']
    
    # 2. 計算持有 N 個月期間的「最低價」
    # rolling(trading_days).min() 是往回看，所以我們要 shift 讓它變成「從今天開始往後看」
    # 使用逆向 rolling 技巧：
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=trading_days)
    backtest_df['Future_Min'] = backtest_df['Close'].rolling(window=indexer, min_periods=1).min()
    
    # 移除最後 N 個月 (因為沒有未來的資料)
    backtest_df = backtest_df.dropna()
    
    if backtest_df.empty:
        return 0, 0, 0 # 資料不足
    
    total_samples = len(backtest_df)
    
    # 統計 A: 正報酬機率
    positive_count = len(backtest_df[backtest_df['Return'] > 0])
    positive_prob = (positive_count / total_samples) * 100
    
    # 統計 B: KI 跌破率 (Knock-In Probability)
    # 條件：期間最低價 < 進場價 * (KI% / 100)
    backtest_df['Ki_Price'] = backtest_df['Close'] * (ki_percent / 100)
    ki_breach_count = len(backtest_df[backtest_df['Future_Min'] < backtest_df['Ki_Price']])
    ki_prob = (ki_breach_count / total_samples) * 100
    
    return positive_prob, ki_prob, total_samples

def plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st):
    """繪製單一整合圖表"""
    
    # 只取最近 2 年畫圖，以免線條太擠，但均線是依據 10 年算的
    plot_df = df.tail(500).copy()
    
    fig = go.Figure()

    # 1. 股價與均線
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['Close'], mode='lines', name='股價', line=dict(color='black', width=1.5)))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA20'], mode='lines', name='月線', line=dict(color='#3498db', width=1)))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA60'], mode='lines', name='季線', line=dict(color='#f1c40f', width=1)))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA240'], mode='lines', name='年線', line=dict(color='#9b59b6', width=1)))

    # 2. 關鍵價位線 (KO / Strike / KI)
    # 使用 yaxis='y2' 讓文字標籤可以顯示在右側軸，或者直接用 annotation
    
    # KO 線
    fig.add_hline(y=p_ko, line_dash="dash", line_color="red", line_width=2)
    fig.add_annotation(x=1, y=p_ko, xref="paper", yref="y", text=f"KO: {p_ko:.2f}", showarrow=False, xanchor="left", font=dict(color="red"))

    # Strike 線
    fig.add_hline(y=p_st, line_dash="solid", line_color="green", line_width=2)
    fig.add_annotation(x=1, y=p_st, xref="paper", yref="y", text=f"Strike: {p_st:.2f}", showarrow=False, xanchor="left", font=dict(color="green"))

    # KI 線
    fig.add_hline(y=p_ki, line_dash="dot", line_color="orange", line_width=2)
    fig.add_annotation(x=1, y=p_ki, xref="paper", yref="y", text=f"KI: {p_ki:.2f}", showarrow=False, xanchor="left", font=dict(color="orange"))

    # 3. 設定範圍與版面
    # 確保所有線都在視野內
    all_prices = [p_ko, p_ki, p_st, plot_df['Close'].max(), plot_df['Close'].min()]
    y_min, y_max = min(all_prices)*0.9, max(all_prices)*1.05

    fig.update_layout(
        title=f"{ticker} - 走勢與關鍵價位",
        height=500,
        margin=dict(r=80), # 右邊留白給文字
        xaxis_title="日期",
        yaxis_title="價格",
        yaxis_range=[y_min, y_max],
        hovermode="x unified",
        legend=dict(orientation="h", y=1.02, x=0)
    )
    
    return fig

# --- 4. 執行邏輯 ---

if run_btn:
    ticker_list = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]
    
    if not ticker_list:
        st.warning("請輸入代碼")
    else:
        for ticker in ticker_list:
            # 1. 抓資料
            with st.spinner(f"正在分析 {ticker} ..."):
                df, err = get_stock_data_10y(ticker)
            
            if err:
                st.error(f"{ticker} 讀取失敗: {err}")
                continue
                
            # 2. 計算價位
            try:
                current_price = float(df['Close'].iloc[-1])
                p_ko = current_price * (ko_pct / 100)
                p_st = current_price * (strike_pct / 100)
                p_ki = current_price * (ki_pct / 100)
            except:
                st.error(f"{ticker} 價格計算錯誤")
                continue

            # 3. 執行回測
            pos_prob, ki_prob, samples = run_backtest(df, ki_pct, period_months)

            # 4. 顯示結果介面
            st.markdown(f"### 📌 標的：{ticker}")
            
            # 第一排：價格資訊
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新收盤價", f"{current_price:.2f}")
            c2.metric("KO 價格", f"{p_ko:.2f}")
            c3.metric("Strike 價格", f"{p_st:.2f}")
            c4.metric("KI 價格", f"{p_ki:.2f}")

            # 第二排：回測數據 (重點功能)
            st.markdown(f"#### 📜 過去 10 年歷史回測 (每 {period_months} 個月為一期)")
            
            m1, m2, m3 = st.columns([1, 1, 2])
            
            # 顯示正報酬機率
            m1.metric(
                label="股價上漲機率 (Win Rate)",
                value=f"{pos_prob:.1f}%",
                help=f"統計過去 10 年，任意時間點買進 {ticker} 並持有 {period_months} 個月，結算時報酬率為正的機率。"
            )
            
            # 顯示 KI 跌破率
            # 顏色邏輯：機率越低越安全(綠)，越高越危險(紅)
            ki_color = "normal" if ki_prob < 20 else "inverse" 
            m2.metric(
                label="觸及 KI 風險機率",
                value=f"{ki_prob:.1f}%",
                delta_color=ki_color,
                help=f"統計過去 10 年，任意時間點進場，在 {period_months} 個月內，股價曾經「跌破」進場時設定之 KI ({ki_pct}%) 的機率。"
            )
            
            m3.info(f"""
            **回測解讀：**
            若您在過去 10 年的任意一天承作此結構型商品 (KI={ki_pct}%)：
            - 有 **{ki_prob:.1f}%** 的機率會發生敲入 (跌破 KI)。
            - 有 **{100-ki_prob:.1f}%** 的機率可以安全度過 (從未跌破 KI)。
            *(樣本數：共檢測 {samples} 個滾動區間)*
            """)

            # 5. 顯示圖表
            fig = plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st)
            st.plotly_chart(fig, use_container_width=True)
            
            st.markdown("---")

else:
    st.info("👈 請在左側設定參數，按下「開始分析」。")
