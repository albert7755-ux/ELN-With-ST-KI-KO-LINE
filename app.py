import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品關鍵價位分析", layout="wide")
st.title("📉 結構型商品 - 關鍵價位三視圖 (KO / KI / Strike)")
st.markdown("輸入股票代碼與自訂關鍵價位，系統將調閱歷史走勢並繪製防線。")
st.divider()

# --- 2. 側邊欄：設定區 ---
st.sidebar.header("1️⃣ 參數設定")

# 2.1 股票代碼與期間
ticker = st.sidebar.text_input("股票代碼 (Yahoo Finance 格式)", value="NVDA", help="美股請打代碼 (如 AAPL)，台股請加 .TW (如 2330.TW)")
lookback = st.sidebar.selectbox("歷史回測期間", ["3個月", "6個月", "1年", "Year to Date (今年以來)"], index=2)

st.sidebar.divider()

# 2.2 關鍵價位設定 (依照您的要求設定預設值)
st.sidebar.subheader("2️⃣ 結構條件")
ko_price = st.sidebar.number_input("KO (敲出價 - 上方)", value=100.0, step=1.0, format="%.2f")
ki_price = st.sidebar.number_input("KI (敲入價 - 下方)", value=65.0, step=1.0, format="%.2f")
strike_price = st.sidebar.number_input("ST (期初/執行價)", value=80.0, step=1.0, format="%.2f")

st.sidebar.markdown("---")

# 2.3 執行按鈕 (放在設定下方)
run_btn = st.sidebar.button("🚀 執行分析", type="primary")

# --- 3. 核心邏輯 ---

# 定義一個安全的資料讀取函數
def fetch_stock_data(ticker, period_option):
    try:
        # 設定時間範圍
        end_date = datetime.now()
        if period_option == "3個月": start_date = end_date - timedelta(days=90)
        elif period_option == "6個月": start_date = end_date - timedelta(days=180)
        elif period_option == "1年": start_date = end_date - timedelta(days=365)
        else: start_date = datetime(end_date.year, 1, 1)

        # 下載資料
        df_raw = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if df_raw.empty:
            return None, f"找不到代碼 {ticker} 的資料，請檢查拼字或後綴。"

        # 【關鍵修正】強制清理資料格式，解決 Series to float 錯誤
        df = df_raw.reset_index()
        
        # 1. 處理 MultiIndex (例如 ('Close', 'NVDA') -> 'Close')
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        # 2. 移除重複欄位
        df = df.loc[:, ~df.columns.duplicated()]
        
        # 3. 確保有 Close 欄位
        if 'Close' not in df.columns:
            return None, "資料來源缺少收盤價欄位。"

        # 只取需要的欄位
        df = df[['Date', 'Close']].copy()
        
        return df, None

    except Exception as e:
        return None, str(e)

# 定義通用繪圖函數
def plot_chart(df, title, line_price, line_color, line_name):
    fig = go.Figure()
    
    # 1. 畫股價走勢
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df['Close'],
        mode='lines', name=ticker,
        line=dict(color='#1f77b4', width=2)
    ))

    # 2. 畫關鍵價位虛線
    fig.add_hline(
        y=line_price, 
        line_dash="dash", # 虛線
        line_color=line_color, 
        line_width=2,
        annotation_text=f"{line_name}: {line_price:.2f}", 
        annotation_position="top left" if line_name == "KO" else "bottom left"
    )

    # 自動調整 Y 軸範圍，確保線看得到
    all_vals = df['Close'].tolist() + [line_price]
    y_min, y_max = min(all_vals) * 0.9, max(all_vals) * 1.1

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

# --- 4. 執行流程 ---

if run_btn:
    with st.spinner(f"正在分析 {ticker} 走勢..."):
        df_data, error_msg = fetch_stock_data(ticker, lookback)
        
        if error_msg:
            st.error(f"❌ 錯誤: {error_msg}")
        else:
            # 取得最新價格 (安全轉型)
            try:
                last_val = df_data['Close'].iloc[-1]
                # 如果是 Series (單一元素)，轉為純量
                if hasattr(last_val, 'item'):
                    current_price = float(last_val.item())
                else:
                    current_price = float(last_val)
            except:
                current_price = 0.0

            st.success(f"✅ 資料讀取成功！{ticker} 最新收盤價: **{current_price:.2f}**")
            
            # 顯示比較狀態
            col_info1, col_info2, col_info3 = st.columns(3)
            
            # KO 狀態
            ko_dist = (ko_price - current_price) / current_price * 100
            if current_price >= ko_price:
                col_info1.metric("KO (敲出) 狀態", "已敲出! 🎉", f"高於 KO {current_price - ko_price:.2f}")
            else:
                col_info1.metric("KO (敲出) 狀態", "未敲出", f"距離 {ko_dist:.2f}%")
                
            # KI 狀態
            # 檢查歷史是否曾跌破 KI
            ki_hits = df_data[df_data['Close'] <= ki_price]
            has_ki = not ki_hits.empty
            ki_dist = (current_price - ki_price) / current_price * 100
            
            if has_ki:
                col_info2.metric("KI (敲入) 狀態", "曾跌破 (危險) ⚠️", f"最低曾至 {df_data['Close'].min():.2f}", delta_color="inverse")
            else:
                col_info2.metric("KI (敲入) 狀態", "安全 (未跌破)", f"緩衝 {ki_dist:.2f}%")

            # Strike 狀態
            st_diff = (current_price - strike_price) / strike_price * 100
            col_info3.metric("與 ST (執行價) 距離", f"{st_diff:+.2f}%", f"現價 {current_price:.2f}")

            st.divider()

            # --- 繪製三張圖 ---
            c1, c2, c3 = st.columns(3)

            # 圖 1: KO
            with c1:
                st.subheader("🚀 KO 敲出觀察")
                fig_ko = plot_chart(df_data, f"KO 價格: {ko_price}", ko_price, "red", "KO")
                # 加強 KO 區域標示
                fig_ko.add_hrect(y0=ko_price, y1=max(df_data['Close'].max(), ko_price)*1.1, line_width=0, fillcolor="red", opacity=0.1, layer="below")
                st.plotly_chart(fig_ko, use_container_width=True)

            # 圖 2: KI
            with c2:
                st.subheader("🛡️ KI 敲入觀察")
                fig_ki = plot_chart(df_data, f"KI 價格: {ki_price}", ki_price, "orange", "KI")
                # 加強 KI 區域標示
                fig_ki.add_hrect(y0=min(df_data['Close'].min(), ki_price)*0.9, y1=ki_price, line_width=0, fillcolor="orange", opacity=0.1, layer="below")
                # 標記跌破點
                if has_ki:
                    fig_ki.add_trace(go.Scatter(x=ki_hits['Date'], y=ki_hits['Close'], mode='markers', marker=dict(color='red', symbol='x'), name='跌破點'))
                st.plotly_chart(fig_ki, use_container_width=True)

            # 圖 3: ST
            with c3:
                st.subheader("⚖️ ST 執行價觀察")
                fig_st = plot_chart(df_data, f"ST 價格: {strike_price}", strike_price, "green", "ST")
                st.plotly_chart(fig_st, use_container_width=True)

else:
    st.info("👈 請在左側設定參數，並點擊「執行分析」按鈕開始。")
    # 預設畫面
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown("### 等待執行...")
    with c2: st.markdown("### 等待執行...")
    with c3: st.markdown("### 等待執行...")
