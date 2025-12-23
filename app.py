import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品戰情室 (V7.0)", layout="wide")
st.title("📊 結構型商品 - 滾動回測視覺化")
st.markdown("""
利用過去 10 年數據進行滾動回測，並以 **Bar 圖** 呈現每一期的最終結果：
* **綠色 Bar**：安全 (拿回本金)。
* **紅色 Bar**：接股票 (虧損幅度)。
""")
st.divider()

# --- 2. 側邊欄：參數設定 ---
st.sidebar.header("1️⃣ 輸入標的")
default_tickers = "NVDA, TSLA, 2330.TW"
tickers_input = st.sidebar.text_area("股票代碼 (逗號分隔)", value=default_tickers, height=80)

st.sidebar.divider()
st.sidebar.header("2️⃣ 結構條件 (%)")
st.sidebar.info("以該期「進場價」為 100% 基準：")
ko_pct = st.sidebar.number_input("KO (敲出價 %)", value=103.0, step=0.5, format="%.1f")
strike_pct = st.sidebar.number_input("Strike (執行價 %)", value=100.0, step=1.0, format="%.1f")
ki_pct = st.sidebar.number_input("KI (敲入價 %)", value=65.0, step=1.0, format="%.1f")

st.sidebar.divider()
st.sidebar.header("3️⃣ 回測參數設定")
period_months = st.sidebar.number_input("產品/觀察天期 (月)", min_value=1, max_value=60, value=6, step=1)

run_btn = st.sidebar.button("🚀 開始分析", type="primary")

# --- 3. 核心函數 ---

def get_stock_data_10y(ticker):
    try:
        df = yf.download(ticker, period="10y", progress=False)
        if df.empty: return None, f"找不到 {ticker}"
        
        df = df.reset_index()
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.loc[:, ~df.columns.duplicated()]
        
        if 'Close' not in df.columns: return None, "無收盤價資料"

        df['Date'] = pd.to_datetime(df['Date'])
        df['Close'] = pd.to_numeric(df['Close'], errors='coerce')
        df = df.dropna(subset=['Close'])

        # 均線 (畫主圖用)
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA240'] = df['Close'].rolling(window=240).mean()
        
        return df, None
    except Exception as e:
        return None, str(e)

def run_rolling_backtest(df, ki_pct, strike_pct, months):
    """
    執行滾動回測，並準備畫 Bar 圖的資料
    """
    trading_days = int(months * 21)
    
    bt = df[['Date', 'Close']].copy()
    bt.columns = ['Start_Date', 'Start_Price']
    
    # 未來價格
    bt['End_Date'] = bt['Start_Date'].shift(-trading_days)
    bt['Final_Price'] = bt['Start_Price'].shift(-trading_days)
    
    # 期間最低價
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=trading_days)
    bt['Min_Price_During'] = bt['Start_Price'].rolling(window=indexer, min_periods=1).min()
    
    bt = bt.dropna()
    
    if bt.empty: return None, None
    
    # 判斷邏輯
    bt['KI_Level'] = bt['Start_Price'] * (ki_pct / 100)
    bt['Strike_Level'] = bt['Start_Price'] * (strike_pct / 100)
    
    bt['Touched_KI'] = bt['Min_Price_During'] < bt['KI_Level']
    bt['Below_Strike'] = bt['Final_Price'] < bt['Strike_Level']
    
    # 定義結果與顏色
    # 我們要畫 Bar 圖，Y軸代表「期末表現 (相對於 Strike 的距離 %)」
    # 邏輯：
    # 1. 如果沒觸及 KI，或是觸及但漲回 -> 視為 0 (或小正值代表拿回本金，這裡設為 0 代表平盤安全)
    # 2. 如果觸及 KI 且低於 Strike -> 顯示負值 (虧損幅度)
    
    def calculate_pnl_gap(row):
        # 情況 A: 接股票 (虧損)
        if row['Touched_KI'] and row['Below_Strike']:
            # 回傳負數百分比，例如 -15 代表比 Strike 低 15%
            return ((row['Final_Price'] - row['Strike_Level']) / row['Strike_Level']) * 100
        
        # 情況 B: 安全 (拿回本金)
        # 為了視覺化，我們給它一個很小的正值，或者直接顯示 0，或者顯示其實際漲幅(但不超過 Cap)
        # 這裡為了凸顯「安全」，我們顯示其實際漲幅，但如果是單純拿回本金結構，通常設為 0
        # 為了讓綠色 Bar 出現，我們顯示它相對於 Strike 的距離 (正數)
        gap = ((row['Final_Price'] - row['Strike_Level']) / row['Strike_Level']) * 100
        return max(0, gap) # 確保不顯示負數 (因為那是上面情況 A 的事)

    bt['Bar_Value'] = bt.apply(calculate_pnl_gap, axis=1)
    
    # 設定顏色
    # 紅色 = 接股票
    # 綠色 = 安全
    bt['Color'] = np.where((bt['Touched_KI'] & bt['Below_Strike']), 'red', 'green')
    
    # 統計數據
    total = len(bt)
    safe_count = len(bt[bt['Color'] == 'green'])
    safety_prob = (safe_count / total) * 100
    
    return bt, safety_prob

def plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st):
    """主圖：股價走勢 + 關鍵位"""
    plot_df = df.tail(500).copy()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['Close'], mode='lines', name='股價', line=dict(color='black', width=1.5)))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA20'], mode='lines', name='月線', line=dict(color='#3498db', width=1)))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA60'], mode='lines', name='季線', line=dict(color='#f1c40f', width=1)))
    fig.add_trace(go.Scatter(x=plot_df['Date'], y=plot_df['MA240'], mode='lines', name='年線', line=dict(color='#9b59b6', width=1)))

    fig.add_hline(y=p_ko, line_dash="dash", line_color="red", line_width=2)
    fig.add_annotation(x=1, y=p_ko, xref="paper", yref="y", text=f"KO: {p_ko:.2f}", showarrow=False, xanchor="left", font=dict(color="red"))

    fig.add_hline(y=p_st, line_dash="solid", line_color="green", line_width=2)
    fig.add_annotation(x=1, y=p_st, xref="paper", yref="y", text=f"Strike: {p_st:.2f}", showarrow=False, xanchor="left", font=dict(color="green"))

    fig.add_hline(y=p_ki, line_dash="dot", line_color="orange", line_width=2)
    fig.add_annotation(x=1, y=p_ki, xref="paper", yref="y", text=f"KI: {p_ki:.2f}", showarrow=False, xanchor="left", font=dict(color="orange"))

    # 自動調整範圍
    all_prices = [p_ko, p_ki, p_st, plot_df['Close'].max(), plot_df['Close'].min()]
    y_min, y_max = min(all_prices)*0.9, max(all_prices)*1.05

    fig.update_layout(title=f"{ticker} - 走勢與關鍵價位", height=400, margin=dict(r=80), xaxis_title="日期", yaxis_title="價格", yaxis_range=[y_min, y_max], hovermode="x unified", legend=dict(orientation="h", y=1.02, x=0))
    return fig

def plot_rolling_bar_chart(bt_data, ticker):
    """
    繪製滾動回測 Bar 圖
    X軸：進場日期
    Y軸：期末表現 % (相對於 Strike)
    """
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=bt_data['Start_Date'],
        y=bt_data['Bar_Value'],
        marker_color=bt_data['Color'],
        name='期末表現'
    ))
    
    # 畫零軸 (Strike 線)
    fig.add_hline(y=0, line_width=1, line_color="black")
    
    fig.update_layout(
        title=f"{ticker} - 滾動回測損益分佈圖 (Rolling Backtest)",
        xaxis_title="進場日期",
        yaxis_title="期末距離 Strike 幅度 (%)",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=False,
        hovermode="x unified"
    )
    
    # 增加註解說明
    fig.add_annotation(
        text="🟩 綠色：安全下莊 (未觸及KI 或 漲回Strike)",
        xref="paper", yref="paper",
        x=0, y=1.1, showarrow=False, font=dict(color="green")
    )
    fig.add_annotation(
        text="🟥 紅色：接股票 (跌破KI 且 低於Strike)",
        xref="paper", yref="paper",
        x=0.5, y=1.1, showarrow=False, font=dict(color="red")
    )
    
    return fig

# --- 4. 執行邏輯 ---

if run_btn:
    ticker_list = [t.strip().upper() for t in tickers_input.split(',') if t.strip()]
    
    if not ticker_list:
        st.warning("請輸入代碼")
    else:
        for ticker in ticker_list:
            st.markdown(f"### 📌 標的：{ticker}")
            
            with st.spinner(f"正在分析 {ticker} ..."):
                df, err = get_stock_data_10y(ticker)
            
            if err:
                st.error(f"{ticker} 讀取失敗: {err}")
                continue
                
            try:
                current_price = float(df['Close'].iloc[-1])
                p_ko = current_price * (ko_pct / 100)
                p_st = current_price * (strike_pct / 100)
                p_ki = current_price * (ki_pct / 100)
            except:
                st.error(f"{ticker} 價格計算錯誤")
                continue

            bt_data, safety_prob = run_rolling_backtest(df, ki_pct, strike_pct, period_months)
            
            if bt_data is None:
                st.warning("資料不足")
                continue

            # --- 顯示區塊 ---
            
            # 1. 價格資訊與勝率
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新收盤價", f"{current_price:.2f}")
            c2.metric("KI 價格", f"{p_ki:.2f}")
            
            safe_color = "normal" if safety_prob > 80 else "inverse"
            c3.metric("歷史安全機率", f"{safety_prob:.1f}%", delta_color=safe_color, help="不接股票的機率")
            c4.metric("歷史接股機率", f"{100-safety_prob:.1f}%", delta_color="inverse", help="需承接股票的機率")

            # 2. 股價走勢圖 (主圖)
            fig_main = plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st)
            st.plotly_chart(fig_main, use_container_width=True)
            
            # 3. 滾動回測 Bar 圖 (新功能)
            st.subheader("📉 歷史回測壓力測試")
            st.caption(f"模擬過去 10 年，每一天進場持有 {period_months} 個月後的結果：")
            fig_bar = plot_rolling_bar_chart(bt_data, ticker)
            st.plotly_chart(fig_bar, use_container_width=True)

            st.markdown("---")

else:
    st.info("👈 請在左側設定參數，按下「開始分析」。")
