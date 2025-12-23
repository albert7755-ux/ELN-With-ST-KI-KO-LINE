import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品戰情室 (V8.0)", layout="wide")
st.title("📊 結構型商品 - 歷史回測與風險防禦分析")
st.markdown("""
結合 **視覺化圖表** 與 **深度風險數據**：
1. **防禦力**：計算歷史上「不接股票」的安全機率。
2. **恢復力**：計算萬一接到股票，平均需要等待 **幾天** 才能解套 (回到 Strike)。
3. **可視化**：透過滾動 Bar 圖，一眼看出歷史上的風險分布。
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

        # 均線
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA240'] = df['Close'].rolling(window=240).mean()
        
        return df, None
    except Exception as e:
        return None, str(e)

def run_comprehensive_backtest(df, ki_pct, strike_pct, months):
    """
    綜合回測：同時計算「回本天數」與準備「Bar圖資料」
    """
    trading_days = int(months * 21)
    
    # 建立回測資料
    bt = df[['Date', 'Close']].copy()
    bt.columns = ['Start_Date', 'Start_Price']
    
    # 1. 計算週期結束資訊
    bt['End_Date'] = bt['Start_Date'].shift(-trading_days)
    bt['Final_Price'] = bt['Start_Price'].shift(-trading_days)
    
    # 2. 期間最低價
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=trading_days)
    bt['Min_Price_During'] = bt['Start_Price'].rolling(window=indexer, min_periods=1).min()
    
    bt = bt.dropna() # 移除未完成的週期
    
    if bt.empty: return None, None
    
    # 3. 計算關鍵價位
    bt['KI_Level'] = bt['Start_Price'] * (ki_pct / 100)
    bt['Strike_Level'] = bt['Start_Price'] * (strike_pct / 100)
    
    # 4. 判定狀態
    bt['Touched_KI'] = bt['Min_Price_During'] < bt['KI_Level']
    bt['Below_Strike'] = bt['Final_Price'] < bt['Strike_Level']
    
    # 結果判定
    conditions = [
        (bt['Touched_KI'] == True) & (bt['Below_Strike'] == True), # 接股票
        (bt['Touched_KI'] == True) & (bt['Below_Strike'] == False),# 驚險過關
        (bt['Touched_KI'] == False) # 安全
    ]
    choices = ['Loss', 'Safe', 'Safe']
    bt['Result_Type'] = np.select(conditions, choices, default='Unknown')
    
    # --- A. 計算回本天數 (Recovery Days) ---
    loss_indices = bt[bt['Result_Type'] == 'Loss'].index
    recovery_counts = [] 
    stuck_count = 0
    
    for idx in loss_indices:
        row = bt.loc[idx]
        target_price = row['Strike_Level']
        end_date = row['End_Date']
        
        # 往未來找解套日
        future_data = df[(df['Date'] > end_date) & (df['Close'] >= target_price)]
        
        if not future_data.empty:
            days_needed = (future_data.iloc[0]['Date'] - end_date).days
            recovery_counts.append(days_needed)
        else:
            stuck_count += 1 # 至今未解套

    # --- B. 準備 Bar 圖資料 ---
    def calculate_bar_value(row):
        gap = ((row['Final_Price'] - row['Strike_Level']) / row['Strike_Level']) * 100
        if row['Result_Type'] == 'Loss':
            return gap # 負值，顯示虧損幅度
        else:
            return max(0, gap) # 正值，顯示安全距離

    bt['Bar_Value'] = bt.apply(calculate_bar_value, axis=1)
    bt['Color'] = np.where(bt['Result_Type'] == 'Loss', 'red', 'green')

    # --- C. 統計指標 ---
    total = len(bt)
    safe_count = len(bt[bt['Result_Type'] == 'Safe'])
    safety_prob = (safe_count / total) * 100
    
    pos_count = len(bt[bt['Final_Price'] > bt['Start_Price']])
    pos_prob = (pos_count / total) * 100
    
    avg_recovery = np.mean(recovery_counts) if recovery_counts else 0
    
    stats = {
        'safety_prob': safety_prob,
        'positive_prob': pos_prob,
        'loss_count': len(loss_indices),
        'avg_recovery': avg_recovery,
        'stuck_count': stuck_count,
        'total_samples': total
    }
    
    return bt, stats

def plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st):
    """主圖：股價 + 均線 + 關鍵位"""
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

    all_prices = [p_ko, p_ki, p_st, plot_df['Close'].max(), plot_df['Close'].min()]
    y_min, y_max = min(all_prices)*0.9, max(all_prices)*1.05

    fig.update_layout(title=f"{ticker} - 走勢與關鍵價位", height=450, margin=dict(r=80), xaxis_title="日期", yaxis_title="價格", yaxis_range=[y_min, y_max], hovermode="x unified", legend=dict(orientation="h", y=1.02, x=0))
    return fig

def plot_rolling_bar_chart(bt_data, ticker):
    """Bar 圖：顯示回測結果"""
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=bt_data['Start_Date'],
        y=bt_data['Bar_Value'],
        marker_color=bt_data['Color'],
        name='期末表現'
    ))
    fig.add_hline(y=0, line_width=1, line_color="black")
    
    fig.update_layout(
        title=f"{ticker} - 滾動回測損益分佈 (過去10年)",
        xaxis_title="進場日期",
        yaxis_title="期末距離 Strike 幅度 (%)",
        height=350,
        margin=dict(l=20, r=20, t=40, b=20),
        showlegend=False,
        hovermode="x unified"
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

            bt_data, stats = run_comprehensive_backtest(df, ki_pct, strike_pct, period_months)
            
            if bt_data is None:
                st.warning("資料不足")
                continue

            # --- 第一區：價格與關鍵指標 ---
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新收盤價", f"{current_price:.2f}")
            c2.metric("KI 價格 (敲入)", f"{p_ki:.2f}")
            
            # 安全機率
            safe_prob = stats['safety_prob']
            safe_color = "normal" if safe_prob > 80 else "inverse"
            c3.metric("不接股票機率 (安全)", f"{safe_prob:.1f}%", delta_color=safe_color)
            
            # 回本天數
            avg_days = stats['avg_recovery']
            if stats['loss_count'] > 0:
                c4.metric("若接股 平均回本天數", f"{avg_days:.0f} 天")
            else:
                c4.metric("若接股 平均回本天數", "無接股紀錄")

            # --- 第二區：淺藍色底框 (重點解釋區) ---
            # 這是您最喜歡的 V6 解釋風格
            loss_pct = 100 - safe_prob
            stuck_rate = 0
            if stats['loss_count'] > 0:
                stuck_rate = (stats['stuck_count'] / stats['loss_count']) * 100
            
            st.info(f"""
            **📊 歷史回測洞察報告 (過去 10 年，每 {period_months} 個月一期)：**
            
            1.  **安全性分析 (不被換到股票的機率)**：
                在過去 10 年任意時間點進場，有 **{safe_prob:.1f}%** 的機率可以安全拿回本金 (未跌破 KI 或 跌破後漲回)。
                
            2.  **獲利潛力 (正報酬機率)**：
                若不考慮配息，單純看股價，持有期滿後股價上漲的機率為 **{stats['positive_prob']:.1f}%**。
                
            3.  **恢復力分析 (解套時間)**：
                若不幸發生接股票的情況 (機率約 {loss_pct:.1f}%)，根據歷史經驗，**平均等待 {avg_days:.0f} 天** 股價即會漲回 Strike 價格。
                *(註：在所有接股票的案例中，約有 {stuck_rate:.1f}% 的情況截至目前尚未解套)*
            """)

            # --- 第三區：整合走勢圖 ---
            fig_main = plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st)
            st.plotly_chart(fig_main, use_container_width=True)
            
            # --- 第四區：滾動回測 Bar 圖 ---
            st.subheader("📉 歷史滾動回測結果 (Rolling Backtest)")
            st.caption("🟩 **綠色**：安全 (拿回本金) ｜ 🟥 **紅色**：接股票 (虧損幅度)")
            fig_bar = plot_rolling_bar_chart(bt_data, ticker)
            st.plotly_chart(fig_bar, use_container_width=True)

            st.markdown("---")

else:
    st.info("👈 請在左側設定參數，按下「開始分析」。")
