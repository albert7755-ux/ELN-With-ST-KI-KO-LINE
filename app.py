import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd

# --- 1. 基礎設定 ---
st.set_page_config(page_title="結構型商品關鍵價位檢視", layout="wide")
st.title("📉 結構型商品 - 關鍵價位三視圖 (KO / KI / ST)")
st.markdown("此工具將標的物走勢分別與 KO、KI、ST 三個關鍵價位進行獨立比對，清晰呈現觸價風險。")
st.divider()

# --- 2. 側邊欄：參數設定與模擬資料 ---
st.sidebar.header("⚙️ 參數設定")

# 設定關鍵價位 (以百分比計)
st_level = 100.0 # 期初價格設為基準 100
ko_pct = st.sidebar.slider("KO 敲出價 (%)", min_value=101.0, max_value=120.0, value=105.0, step=0.5)
ki_pct = st.sidebar.slider("KI 敲入價 (%)", min_value=50.0, max_value=99.0, value=70.0, step=1.0)

# 計算實際數值
ko_level = st_level * (ko_pct / 100)
ki_level = st_level * (ki_pct / 100)

st.sidebar.markdown("---")
st.sidebar.write(f"**ST (執行價):** {st_level:.2f}")
st.sidebar.write(f"**KO (敲出價):** {ko_level:.2f}")
st.sidebar.write(f"**KI (敲入價):** {ki_level:.2f}")
st.sidebar.markdown("---")

# 模擬按鈕
start_simulation = st.sidebar.button("🔄 重新模擬走勢", type="primary")

# --- 3. 資料模擬函數 ---
def simulate_path(start_price, days=252, volatility=0.2):
    """
    模擬一條幾何布朗運動的價格路徑 (僅供視覺化參考)
    """
    np.random.seed(int(pd.Timestamp.now().timestamp()) if start_simulation else 42)
    dt = 1 / days
    mu = 0.05 # 假設一個小的向上漂移項
    sigma = volatility
    
    # 生成隨機漫步
    returns = np.random.normal(loc=(mu - 0.5 * sigma**2) * dt, scale=sigma * np.sqrt(dt), size=days)
    price_path = start_price * (np.cumprod(np.exp(returns)))
    
    # 插入期初價格在第一天
    price_path = np.insert(price_path, 0, start_price)
    
    # 為了演示效果，強制讓中間一段時間跌破 KI，最後又拉回
    mid_point = int(days / 2)
    end_point = int(days * 0.8)
    
    # 製造一個下跌波段觸及 KI
    downward_shock = np.linspace(0, -1 * (start_price - ki_level) * 1.2, num=(end_point - mid_point))
    price_path[mid_point:end_point] += downward_shock
    
    # 確保價格不為負
    price_path = np.maximum(price_path, 1.0)
    
    days_axis = list(range(len(price_path)))
    return pd.DataFrame({'Day': days_axis, 'Price': price_path})

# 執行模擬
df = simulate_path(st_level)
y_min = df['Price'].min() * 0.9
y_max = max(df['Price'].max(), ko_level) * 1.1

# --- 4. 繪圖函數 (通用基礎底圖) ---
def get_base_figure(title):
    fig = go.Figure()
    # 加入標的走勢線 (所有圖都一樣)
    fig.add_trace(go.Scatter(
        x=df['Day'], y=df['Price'],
        mode='lines', name='標的走勢',
        line=dict(color='#1f77b4', width=2)
    ))
    fig.update_layout(
        title=title,
        xaxis_title="觀察天數",
        yaxis_title="價格 (Rebased to 100)",
        yaxis_range=[y_min, y_max],
        height=400,
        margin=dict(l=20, r=20, t=50, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    return fig

# --- 5. 建立三張獨立圖表 ---

# === 圖 1: KO 檢視 ===
fig_ko = get_base_figure("🎯 圖一：KO (敲出價) 檢視")
# 畫 KO 線
fig_ko.add_hline(y=ko_level, line_dash="dash", line_color="red", annotation_text=f"KO: {ko_level:.2f}", annotation_position="top left")
# 畫 KO 觸發區域 (紅色陰影)
fig_ko.add_hrect(y0=ko_level, y1=y_max, line_width=0, fillcolor="red", opacity=0.1, layer="below")
fig_ko.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(color='red', symbol='square', opacity=0.5), name='敲出區 (提早結束)'))


# === 圖 2: KI 檢視 ===
fig_ki = get_base_figure("⚠️ 圖二：KI (敲入價) 檢視")
# 畫 KI 線
fig_ki.add_hline(y=ki_level, line_dash="dot", line_color="orange", annotation_text=f"KI: {ki_level:.2f}", annotation_position="bottom left")
# 畫 KI 風險區域 (橘色陰影)
fig_ki.add_hrect(y0=y_min, y1=ki_level, line_width=0, fillcolor="orange", opacity=0.1, layer="below")
fig_ki.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(color='orange', symbol='square', opacity=0.5), name='敲入區 (風險產生)'))
# 標記實際跌破的點
ki_breach = df[df['Price'] < ki_level]
if not ki_breach.empty:
    fig_ki.add_trace(go.Scatter(
        x=ki_breach['Day'], y=ki_breach['Price'],
        mode='markers', name='已觸及KI點位',
        marker=dict(color='red', size=6, symbol='x')
    ))


# === 圖 3: ST 檢視 ===
fig_st = get_base_figure("🏁 圖三：ST (執行價/期初價) 檢視")
# 畫 ST 線
fig_st.add_hline(y=st_level, line_width=2, line_color="green", annotation_text=f"ST (期初): {st_level:.2f}", annotation_position="right")
# 畫期末損益分界
fig_st.add_hrect(y0=y_min, y1=st_level, line_width=0, fillcolor="green", opacity=0.05, layer="below")
fig_st.add_trace(go.Scatter(x=[None], y=[None], mode='markers', marker=dict(color='green', symbol='square', opacity=0.3), name='期末潛在虧損區 (若曾觸及KI)'))


# --- 6. 頁面佈局 (三欄並列) ---
c1, c2, c3 = st.columns(3)

with c1:
    st.plotly_chart(fig_ko, use_container_width=True)
    st.caption("觀察重點：價格是否**高於紅線**？若觀察日高於此線，產品提前出場 (獲利結算)。")

with c2:
    st.plotly_chart(fig_ki, use_container_width=True)
    st.caption("觀察重點：價格是否曾經**低於橘線**？若期間內曾跌破此線，下方保護消失，期末可能面臨本金損失。")

with c3:
    st.plotly_chart(fig_st, use_container_width=True)
    st.caption("觀察重點：期末價格與綠線的關係。若曾觸及 KI 且期末價格低於 ST，將產生虧損 (接股票)。")

# --- 7. 狀態摘要 ---
st.divider()
st.subheader("📊 模擬結果摘要")
has_touched_ki = df['Price'].min() < ki_level
has_touched_ko = df['Price'].max() > ko_level
final_price = df['Price'].iloc[-1]

col_res1, col_res2, col_res3 = st.columns(3)
col_res1.metric("曾觸及 KI (敲入)", "是 (高風險)" if has_touched_ki else "否 (安全)", delta_color="inverse" if has_touched_ki else "normal")
col_res2.metric("曾觸及 KO (敲出)", "是 (提前結束)" if has_touched_ko else "否 (持有至到期)")
col_res3.metric("期末價格 vs ST", f"{final_price:.2f} ({((final_price/st_level)-1)*100:+.2f}%)", delta_color="normal" if final_price >= st_level else "inverse")

if has_touched_ki and final_price < st_level:
    st.error("⚠️ **風險警示**：此模擬路徑顯示，標的曾跌破 KI 且期末價格低於 ST。若為實際商品，投資人將面臨本金虧損 (通常需以 ST 價格承接下跌的股票)。")
elif has_touched_ko:
    st.success("💰 **獲利提示**：此模擬路徑顯示，標的曾觸及 KO。若在觀察日觸及，產品將提前獲利出場。")
else:
    st.info("ℹ️ **持有狀態**：此模擬路徑未觸及 KO，也未跌破 KI。通常可領取固定配息至期末拿回本金。")
