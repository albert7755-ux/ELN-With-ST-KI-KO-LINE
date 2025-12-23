import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品戰情室 (V6.0)", layout="wide")
st.title("📊 結構型商品 - 風險回測與「接股後回本」分析")
st.markdown("""
本系統利用過去 10 年歷史數據進行滾動式回測：
1. **防禦力**：計算不接股票（安全下莊）的機率。
2. **恢復力**：萬一接到股票，歷史數據顯示平均需要 **等待幾天** 股價才能漲回 Strike (解套)。
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
period_months = st.sidebar.number_input("產品/觀察天期 (月)", min_value=1, max_value=60, value=6, step=1)

run_btn = st.sidebar.button("🚀 開始分析", type="primary")

# --- 3. 核心函數 ---

def get_stock_data_10y(ticker):
    """下載過去 10 年資料"""
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

def run_detailed_backtest(df, ki_pct, strike_pct, months):
    """
    執行詳細回測，包含「回本天數」計算
    """
    trading_days = int(months * 21)
    
    # 準備回測資料
    bt = df[['Date', 'Close']].copy()
    bt.columns = ['Start_Date', 'Start_Price']
    
    # 計算週期結束資訊
    bt['End_Date'] = bt['Start_Date'].shift(-trading_days)
    bt['Final_Price'] = bt['Start_Price'].shift(-trading_days)
    
    # 期間最低價
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=trading_days)
    bt['Min_Price_During'] = bt['Start_Price'].rolling(window=indexer, min_periods=1).min()
    
    # 移除未完成的週期
    bt = bt.dropna()
    
    if bt.empty: return None, None
    
    # 計算關鍵價位
    bt['KI_Level'] = bt['Start_Price'] * (ki_pct / 100)
    bt['Strike_Level'] = bt['Start_Price'] * (strike_pct / 100)
    
    # 判定狀態
    bt['Touched_KI'] = bt['Min_Price_During'] < bt['KI_Level']
    bt['Below_Strike'] = bt['Final_Price'] < bt['Strike_Level']
    
    # 判定結果
    conditions = [
        (bt['Touched_KI'] == True) & (bt['Below_Strike'] == True),
        (bt['Touched_KI'] == True) & (bt['Below_Strike'] == False),
        (bt['Touched_KI'] == False)
    ]
    choices = ['接股票 (損)', '觸及KI但漲回 (安)', '未觸及KI (安)']
    bt['Result'] = np.select(conditions, choices, default='未知')
    
    # --- 新增：計算回本天數 (Recovery Analysis) ---
    recovery_days_list = []
    
    # 為了加速，將原始資料轉為 dict 或 list 查詢，或直接用 DataFrame 篩選
    # 這裡使用 iterrows 逐行處理 (資料量約 2500 筆，效能尚可)
    
    bt['Recovery_Days'] = np.nan # 預設 NaN
    bt['Recovery_Status'] = '-'  # 顯示狀態文字
    
    loss_indices = bt[bt['Result'] == '接股票 (損)'].index
    
    recovery_counts = [] # 儲存所有接股票案例的回本天數
    stuck_count = 0      # 統計到現在還沒解套的
    
    for idx in loss_indices:
        row = bt.loc[idx]
        target_price = row['Strike_Level']
        end_date = row['End_Date']
        
        # 從結束日往後找，股價 >= Strike 的第一天
        # 篩選未來數據
        future_data = df[(df['Date'] > end_date) & (df['Close'] >= target_price)]
        
        if not future_data.empty:
            recover_date = future_data.iloc[0]['Date']
            days_needed = (recover_date - end_date).days
            bt.at[idx, 'Recovery_Days'] = days_needed
            bt.at[idx, 'Recovery_Status'] = f"{days_needed} 天"
            recovery_counts.append(days_needed)
        else:
            # 尚未回本 (截至資料庫最後一天)
            bt.at[idx, 'Recovery_Status'] = "尚未回本"
            stuck_count += 1

    # 統計數據
    total_samples = len(bt)
    safe_count = len(bt[bt['Result'] != '接股票 (損)'])
    safety_prob = (safe_count / total_samples) * 100
    
    positive_return_count = len(bt[bt['Final_Price'] > bt['Start_Price']])
    positive_prob = (positive_return_count / total_samples) * 100
    
    # 平均回本天數 (只計算已回本的)
    avg_recovery = np.mean(recovery_counts) if recovery_counts else 0
    max_recovery = np.max(recovery_counts) if recovery_counts else 0
    
    # 回傳統計包
    stats = {
        'safety_prob': safety_prob,
        'positive_prob': positive_prob,
        'total_samples': total_samples,
        'loss_count': len(loss_indices),
        'avg_recovery_days': avg_recovery,
        'stuck_count': stuck_count
    }
    
    return bt, stats

def plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st):
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

    fig.update_layout(title=f"{ticker} - 走勢與關鍵價位", height=500, margin=dict(r=80), xaxis_title="日期", yaxis_title="價格", yaxis_range=[y_min, y_max], hovermode="x unified", legend=dict(orientation="h", y=1.02, x=0))
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

            bt_data, stats = run_detailed_backtest(df, ki_pct, strike_pct, period_months)
            
            if bt_data is None:
                st.warning("資料不足")
                continue

            # --- 第一區：價格 ---
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("最新收盤價", f"{current_price:.2f}")
            c2.metric("KO 價格", f"{p_ko:.2f}")
            c3.metric("Strike 價格", f"{p_st:.2f}")
            c4.metric("KI 價格", f"{p_ki:.2f}")

            # --- 第二區：機率分析 ---
            st.markdown(f"#### 🛡️ 歷史回測機率 (過去10年，每 {period_months} 個月一期)")
            m1, m2, m3 = st.columns(3)
            
            # 1. 安全機率
            safe_prob = stats['safety_prob']
            safe_color = "normal" if safe_prob > 80 else "inverse"
            m1.metric("不接股票機率 (安全)", f"{safe_prob:.1f}%", delta_color=safe_color)
            
            # 2. 平均回本天數 (新功能)
            avg_days = stats['avg_recovery_days']
            if stats['loss_count'] > 0:
                m2.metric("若接股票，平均回本天數", f"{avg_days:.0f} 天", help="統計歷史上發生接股票事件後，股價漲回 Strike 平均需要等待的日曆天數。")
            else:
                m2.metric("若接股票，平均回本天數", "無接股紀錄", help="過去 10 年此條件下未發生接股票事件，故無需回本。")

            # 3. 正報酬機率
            m3.metric("正報酬機率 (股價上漲)", f"{stats['positive_prob']:.1f}%")

            # --- 文字解讀 ---
            loss_pct = 100 - safe_prob
            stuck_rate = 0
            if stats['loss_count'] > 0:
                stuck_rate = (stats['stuck_count'] / stats['loss_count']) * 100
            
            st.info(f"""
            **回測洞察：**
            - **安全性**：過去 10 年任意點進場，有 **{safe_prob:.1f}%** 的機率能全身而退 (拿回本金/現金結算)。
            - **風險與恢復**：僅有 **{loss_pct:.1f}%** 的機率需承接股票。
            - **解套能力**：在那些不幸接到股票的案例中，平均只需持有 **{avg_days:.0f} 天** 股價即漲回 Strike。
              *(註：接股案例中，約有 {stuck_rate:.1f}% 的情況截至目前尚未解套)*
            """)

            # --- 第三區：圖表 ---
            fig = plot_integrated_chart(df, ticker, current_price, p_ko, p_ki, p_st)
            st.plotly_chart(fig, use_container_width=True)
            
            # --- 第四區：詳細數據 ---
            with st.expander(f"📜 查看 {ticker} 詳細回測數據 (包含回本天數)", expanded=False):
                display_df = bt_data[['Start_Date', 'End_Date', 'Start_Price', 'Final_Price', 'Min_Price_During', 'Result', 'Recovery_Status']].copy()
                display_df['Start_Date'] = display_df['Start_Date'].dt.date
                display_df['End_Date'] = display_df['End_Date'].dt.date
                
                display_df['Start_Price'] = display_df['Start_Price'].map('{:.2f}'.format)
                display_df['Final_Price'] = display_df['Final_Price'].map('{:.2f}'.format)
                display_df['Min_Price_During'] = display_df['Min_Price_During'].map('{:.2f}'.format)
                
                # 重新命名欄位以符合中文語境
                display_df.columns = ['進場日', '結算日', '進場價', '結算價', '期間最低價', '結果', '回本等待時間']

                def highlight_status(row):
                    if '接股票' in row['結果']:
                        return ['background-color: #ffe6e6'] * len(row) # 淺紅底
                    return [''] * len(row)

                st.dataframe(display_df.style.apply(highlight_status, axis=1), use_container_width=True)

            st.markdown("---")

else:
    st.info("👈 請在左側設定參數，按下「開始分析」。")
