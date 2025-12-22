import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 網頁設定 ---
st.set_page_config(page_title="ELN 結構型商品分析", layout="wide")
st.title("🏦 ELN 結構型商品 - 互動式分析儀表板")
st.markdown("輸入參數並按下 **「開始計算」**，即可生成分析報告。")

# --- 2. 側邊欄：表單輸入 (按鈕才送出) ---
with st.sidebar.form(key='eln_form'):
    st.header("參數設定")
    
    # 股票代號
    ticker_input = st.text_input("股票代號 (美股代號/台股+TW)", "NVDA")
    
    st.markdown("---")
    # 期初價格 (改為手動輸入，無預設自動抓取功能)
    ref_price_input = st.number_input("期初價格 (Ref Price)", min_value=0.0, value=0.0, step=0.1, format="%.2f")
    
    st.markdown("---")
    st.write("結構條件 (%)")
    ko_pct = st.number_input("KO (提前出場) %", value=100.0)
    strike_pct = st.number_input("Strike (履約) %", value=85.0)
    ki_pct = st.number_input("KI (跌破防守) %", value=60.0)
    
    # 提交按鈕
    submit_button = st.form_submit_button(label='🚀 開始計算')

# --- 3. 核心邏輯 (只有按了按鈕才會執行) ---
if submit_button:
    # 檢查使用者是否輸入了期初價格
    if ref_price_input <= 0:
        st.warning("⚠️ 請輸入有效的「期初價格 (Ref Price)」才能開始計算。")
        st.stop()

    ticker = ticker_input.upper().strip()
    
    try:
        with st.spinner(f"正在抓取 {ticker} 資料並計算中..."):
            # 抓取資料 (抓 800 天以計算年線)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=800)
            
            # yfinance 下載
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
            
            if df.empty:
                st.error(f"❌ 找不到代號 {ticker}，請確認輸入正確。")
                st.stop()

            # --- 資料清洗 (Fix for yfinance v0.2.40+) ---
            # 1. 處理多層索引
            if isinstance(df.columns, pd.MultiIndex):
                try:
                    if ticker in df.columns.get_level_values(1): 
                        df = df.xs(key=ticker, axis=1, level=1)
                    else:
                        df.columns = df.columns.get_level_values(0)
                except:
                    df.columns = df.columns.get_level_values(0)

            # 2. 移除重複欄位
            df = df.loc[:, ~df.columns.duplicated()]

            # 3. 確保 Close 是單一欄位
            if isinstance(df['Close'], pd.DataFrame):
                df['Close'] = df['Close'].iloc[:, 0]
            # -------------------------------------------

            # 取得最新資訊
            current_price = float(df['Close'].iloc[-1])
            current_date = df.index[-1].strftime('%Y-%m-%d')
            
            # 使用使用者輸入的 Ref Price
            ref_price = ref_price_input
            
            # 計算結構點位
            ko_price = ref_price * (ko_pct / 100)
            strike_price = ref_price * (strike_pct / 100)
            ki_price = ref_price * (ki_pct / 100)

            # 計算均線
            df['MA20'] = df['Close'].rolling(window=20).mean()
            df['MA60'] = df['Close'].rolling(window=60).mean()
            df['MA240'] = df['Close'].rolling(window=240).mean()

            # --- 顯示數據卡片 ---
            st.success(f"✅ 計算完成 (資料日期: {current_date})")
            
            col1, col2, col3, col4 = st.columns(4)
            
            # 計算現價與 Ref 的距離
            dist_ref = (current_price - ref_price) / ref_price * 100
            col1.metric("標的現價", f"${current_price:.2f}", f"{dist_ref:+.2f}% (vs Ref)")
            
            col2.metric("KO 價格", f"${ko_price:.2f}", f"{ko_pct}%")
            col3.metric("Strike 價格", f"${strike_price:.2f}", f"{strike_pct}%")
            
            # KI 距離
            dist_to_ki = (current_price - ki_price) / current_price * 100
            ki_delta_color = "normal" if dist_to_ki > 5 else "inverse" # 距離太近變紅色
            col4.metric("KI 價格", f"${ki_price:.2f}", f"距離 {dist_to_ki:.1f}%", delta_color=ki_delta_color)

            # --- 圖表 1: 走勢圖 ---
            st.subheader(f"📈 {ticker} 股價走勢與結構防守線")
            
            fig = go.Figure()
            
            # 只畫最近 1.5 年 (約 380 交易日)
            plot_df = df.iloc[-380:] 
            
            # 股價線
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['Close'], mode='lines', name='收盤價', line=dict(color='#1f77b4', width=3)))
            
            # 均線
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA20'], mode='lines', name='月線 (20MA)', line=dict(color='purple', width=1)))
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA60'], mode='lines', name='季線 (60MA)', line=dict(color='green', width=1)))
            fig.add_trace(go.Scatter(x=plot_df.index, y=plot_df['MA240'], mode='lines', name='年線 (240MA)', line=dict(color='brown', width=1)))
            
            # 結構線 (KO/Strike/KI)
            fig.add_hline(y=ko_price, line_dash="solid", line_color="red", annotation_text=f"KO ${ko_price:.1f}", annotation_position="top right")
            fig.add_hline(y=strike_price, line_dash="dash", line_color="green", annotation_text=f"Strike ${strike_price:.1f}", annotation_position="bottom right")
            fig.add_hline(y=ki_price, line_dash="dash", line_color="orange", annotation_text=f"KI ${ki_price:.1f}", annotation_position="bottom right")
            
            fig.update_layout(height=600, hovermode="x unified", xaxis_title="日期", yaxis_title="價格")
            st.plotly_chart(fig, use_container_width=True)

            # --- 圖表 2: 勝率分析 ---
            st.subheader("📊 歷史持有勝率 (Backtest)")
            st.markdown("計算過去 2 年內，若在任意時間點買進並持有以下天期，獲得**正報酬**的機率。")
            
            periods = {'1個月': 21, '3個月': 63, '6個月': 126, '1年': 252}
            win_data = []
            
            for label, days in periods.items():
                ret = df['Close'].pct_change(periods=days).dropna()
                if len(ret) > 0:
                    win_rate = (ret > 0).mean() * 100
                else:
                    win_rate = 0
                win_data.append({"期間": label, "勝率": win_rate})
                
            win_df = pd.DataFrame(win_data)
            
            # 畫長條圖
            bar_fig = go.Figure(go.Bar(
                x=win_df['期間'], 
                y=win_df['勝率'],
                text=win_df['勝率'].apply(lambda x: f"{x:.1f}%"),
                textposition='auto',
                marker_color=['#a5d6a7', '#66bb6a', '#43a047', '#1b5e20']
            ))
            bar_fig.update_layout(height=400, yaxis_title="勝率 (%)", yaxis_range=[0, 110])
            st.plotly_chart(bar_fig, use_container_width=True)

    except Exception as e:
        st.error(f"發生錯誤: {e}")

else:
    # 尚未按下按鈕時的提示畫面
    st.info("👈 請在左側輸入參數，並按下 **「開始計算」** 按鈕來生成報告。")
