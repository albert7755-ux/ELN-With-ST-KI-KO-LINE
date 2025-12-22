import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# --- 1. 網頁設定 ---
st.set_page_config(page_title="ELN 多標的結構分析", layout="wide")
st.title("🏦 ELN 結構型商品 - 多標的分析儀表板 (Basket)")
st.markdown("支援 **1~5 檔標的** (Worst-of)。輸入代號並按下 **「開始計算」**，系統將自動抓取最新價格並進行歸一化比較。")

# --- 2. 側邊欄：參數設定 ---
with st.sidebar.form(key='eln_form'):
    st.header("1️⃣ 設定連結標的 (Basket)")
    st.caption("請輸入 1~5 檔股票代號，用逗號隔開")
    # 預設輸入範例
    tickers_input = st.text_input("股票代號", "NVDA, TSLA, AMD")
    
    st.markdown("---")
    st.header("2️⃣ 結構條件 (%)")
    st.caption("期初價格 (Ref) 預設為最新收盤價 (100%)")
    
    col_ko, col_ki = st.columns(2)
    with col_ko:
        ko_pct = st.number_input("KO (出場)", value=100.0)
        strike_pct = st.number_input("Strike (履約)", value=85.0)
    with col_ki:
        ki_pct = st.number_input("KI (防守)", value=60.0)
    
    # 提交按鈕
    submit_button = st.form_submit_button(label='🚀 開始計算')

# --- 3. 核心邏輯 ---
if submit_button:
    # 1. 解析股票代號
    tickers_raw = tickers_input.split(',')
    tickers = [t.strip().upper() for t in tickers_raw if t.strip() != '']
    
    # 限制最多 5 檔
    if len(tickers) > 5:
        st.warning("⚠️ 最多支援 5 檔標的，將只取前 5 檔進行計算。")
        tickers = tickers[:5]
    
    if not tickers:
        st.error("❌ 請至少輸入一檔股票代號。")
        st.stop()

    try:
        with st.spinner(f"正在分析 {len(tickers)} 檔標的: {', '.join(tickers)} ..."):
            # 準備數據容器
            basket_data = {}
            summary_data = []
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=800)
            
            # --- 迴圈抓取每一檔資料 ---
            for t in tickers:
                # 下載資料
                df = yf.download(t, start=start_date, end=end_date, progress=False)
                
                # 資料清洗 (Fix yfinance bug)
                if df.empty:
                    st.toast(f"⚠️ 找不到 {t}，已跳過。", icon="⚠️")
                    continue
                
                if isinstance(df.columns, pd.MultiIndex):
                    try:
                        if t in df.columns.get_level_values(1): 
                            df = df.xs(key=t, axis=1, level=1)
                        else:
                            df.columns = df.columns.get_level_values(0)
                    except:
                        df.columns = df.columns.get_level_values(0)
                
                df = df.loc[:, ~df.columns.duplicated()]
                if isinstance(df['Close'], pd.DataFrame):
                    df['Close'] = df['Close'].iloc[:, 0]

                # 取得關鍵價格
                current_price = float(df['Close'].iloc[-1])
                ref_price = current_price # 預設自動抓最新價 = Ref
                
                # 計算距離 KI 的幅度
                ki_price = ref_price * (ki_pct / 100)
                dist_to_ki = (current_price - ki_price) / current_price * 100
                
                # 存入 summary
                summary_data.append({
                    "代號": t,
                    "現價 (Ref)": current_price,
                    "KI價格": ki_price,
                    "距離KI (%)": dist_to_ki,
                    "最新日期": df.index[-1].strftime('%Y-%m-%d')
                })
                
                # 計算歸一化曲線 (Normalized to 100%)
                # 邏輯：為了畫在同一張圖，我們把所有歷史價格除以 Ref Price (也就是今天的價格)
                # 這樣今天的價格一定是 100%，我們可以清楚看到過去股價相對於現在的位置
                df['Normalized'] = (df['Close'] / ref_price) * 100
                
                basket_data[t] = df

            if not basket_data:
                st.error("❌ 所有代號都無法讀取，請檢查輸入。")
                st.stop()

            # --- 找出 Worst-of (雖然現在剛好都是 100%，但邏輯上我們顯示距離 KI 最近的) ---
            # 這裡因為 Ref=Current，所以大家的 Performance 都是 100%。
            # 但如果我們要模擬 "歷史走勢"，我們看的是各股波動度。
            
            summary_df = pd.DataFrame(summary_data)
            
            # --- 顯示數據摘要 ---
            st.success(f"✅ 分析完成 (基準日: {summary_df['最新日期'].iloc[0]})")
            
            # 使用 Dataframe 顯示詳細資訊
            st.subheader("📋 標的監控清單 (Worst-of 觀察)")
            
            # 格式化顯示
            display_df = summary_df[['代號', '現價 (Ref)', 'KI價格', '距離KI (%)']].copy()
            display_df['現價 (Ref)'] = display_df['現價 (Ref)'].map('${:,.2f}'.format)
            display_df['KI價格'] = display_df['KI價格'].map('${:,.2f}'.format)
            display_df['距離KI (%)'] = display_df['距離KI (%)'].map('{:,.2f}%'.format)
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            # --- 圖表 1: 歸一化走勢圖 (Normalized Performance) ---
            st.subheader(f"📈 多標的績效走勢 (歸一化: Ref=100%)")
            st.caption("此圖表將所有股票的 **期初價格 (Ref)** 設定為 100%，方便比較不同價位股票的相對走勢與結構防守線。")
            
            fig = go.Figure()
            
            # 畫每一檔股票的線
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd'] # 預設五種顏色
            
            for i, (ticker, df) in enumerate(basket_data.items()):
                plot_df = df.iloc[-380:] # 只畫最近 1.5 年
                color = colors[i % len(colors)]
                
                fig.add_trace(go.Scatter(
                    x=plot_df.index, 
                    y=plot_df['Normalized'], 
                    mode='lines', 
                    name=ticker, 
                    line=dict(width=2, color=color)
                ))

            # 畫結構線 (因為是歸一化圖表，所以線是固定的百分比)
            fig.add_hline(y=ko_pct, line_dash="solid", line_color="red", annotation_text=f"KO ({ko_pct}%)", annotation_position="top left")
            fig.add_hline(y=strike_pct, line_dash="dash", line_color="green", annotation_text=f"Strike ({strike_pct}%)", annotation_position="bottom left")
            fig.add_hline(y=ki_pct, line_dash="dash", line_color="orange", annotation_text=f"KI ({ki_pct}%)", annotation_position="bottom left")
            
            # 設定圖表
            fig.update_layout(
                height=600, 
                hovermode="x unified", 
                xaxis_title="日期", 
                yaxis_title="相對價格 (%)",
                yaxis_ticksuffix="%"
            )
            st.plotly_chart(fig, use_container_width=True)

            # --- 圖表 2: 勝率分析 (各別顯示) ---
            st.subheader("📊 歷史持有勝率 (各標的獨立回測)")
            st.markdown("計算過去 2 年，若買進並持有特定天期，獲得正報酬的機率。")
            
            periods = {'1M': 21, '3M': 63, '6M': 126, '1Y': 252}
            
            # 準備畫圖數據
            bar_data = []
            for ticker, df in basket_data.items():
                for label, days in periods.items():
                    ret = df['Close'].pct_change(periods=days).dropna()
                    if len(ret) > 0:
                        win_rate = (ret > 0).mean() * 100
                    else:
                        win_rate = 0
                    bar_data.append({"代號": ticker, "期間": label, "勝率": win_rate})
            
            win_df = pd.DataFrame(bar_data)
            
            # 使用 Grouped Bar Chart
            bar_fig = go.Figure()
            
            for ticker in tickers:
                # 篩選該股票的數據
                t_df = win_df[win_df['代號'] == ticker]
                if t_df.empty: continue
                
                bar_fig.add_trace(go.Bar(
                    x=t_df['期間'],
                    y=t_df['勝率'],
                    name=ticker,
                    text=t_df['勝率'].apply(lambda x: f"{x:.0f}%"),
                    textposition='auto'
                ))

            bar_fig.update_layout(
                barmode='group',
                height=400,
                yaxis_title="正報酬機率 (%)",
                yaxis_range=[0, 110],
                title="各連結標的勝率比較"
            )
            st.plotly_chart(bar_fig, use_container_width=True)

    except Exception as e:
        st.error(f"發生系統錯誤: {e}")

else:
    st.info("👈 請在左側輸入 1~5 檔股票代號，並按 **「🚀 開始計算」**。")
