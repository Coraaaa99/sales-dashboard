import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import requests
import base64
import io

# 设置网页基本配置
st.set_page_config(page_title="商机加微率每日分析", layout="wide")

# ======================
# 🌟 新增：隐藏默认悬浮菜单和按钮，确保截长图完美无遮挡 🌟
# ======================
hide_streamlit_style = """
<style>
/* 隐藏顶部的白条导航栏和右上角菜单 */
header {visibility: hidden;}
#MainMenu {visibility: hidden;}
.stDeployButton {display:none;}
/* 隐藏底部的 Made with Streamlit 水印 */
footer {visibility: hidden;}
/* 隐藏右下角的 Manage app 悬浮按钮 */
.viewerBadge_container {display: none !important;}
.viewerBadge_link {display: none !important;}
</style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.title("📈 门店与专家商机加微率分析看板")
st.markdown("团队成员可随时查看趋势并下载历史数据。仅管理员可上传更新数据。")

# ======================
# GitHub API 数据库与密码配置
# ======================
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
    ADMIN_PASSWORD = st.secrets.get("ADMIN_PASSWORD", "8888") 
    
    FILE_PATH = "门店加微率汇总库.csv" 
    API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    HEADERS = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
except Exception:
    st.error("⚠️ 未在 Streamlit Secrets 中找到 GitHub 密钥配置，请检查。")
    st.stop()

# 1. 启动时从 GitHub 仓库获取历史数据
@st.cache_data(ttl=60) 
def load_historical_data():
    try:
        res = requests.get(API_URL, headers=HEADERS)
        if res.status_code == 200:
            data = res.json()
            content = base64.b64decode(data['content']).decode('utf-8-sig')
            df = pd.read_csv(io.StringIO(content))
            return df, data['sha'] 
        elif res.status_code == 404:
            return pd.DataFrame(), None 
    except Exception as e:
        st.error(f"读取云端历史数据失败: {e}")
    return pd.DataFrame(), None

historical_df, file_sha = load_historical_data()

# 定义一个给表格低于30%标红的通用函数
def color_red_if_low(val):
    if isinstance(val, (int, float)) and val < 0.3:
        return 'background-color: #ffe6e6; color: #cc0000; font-weight: bold'
    return ''

# ======================
# 🔒 管理员专属：新数据上传与合并
# ======================
st.divider()
st.subheader("🔒 管理员数据上传区")
admin_pw = st.text_input("请输入管理员密码以开启上传功能：", type="password")

if admin_pw == ADMIN_PASSWORD:
    uploaded_files = st.file_uploader("📤 请上传当天的 Excel/CSV 数据报表（建议以日期命名，如 2026-03-10.xlsx）", accept_multiple_files=True)

    if uploaded_files:
        new_data = []
        for file in uploaded_files:
            try:
                if file.name.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                date_str = str(os.path.splitext(file.name)[0])
                df['上传日期'] = date_str
                new_data.append(df)
            except Exception as e:
                st.error(f"读取文件 {file.name} 失败: {e}")

        if new_data:
            new_df = pd.concat(new_data, ignore_index=True)
            
            if '商机首次承接区域部门名称' in new_df.columns:
                new_df = new_df[new_df['商机首次承接区域部门名称'] != '合计']
                
            fill_cols = ['商机首次承接区域部门名称', '商机首次承接销售部名称', '商机首次承接经营单元部门名称', '商机首次承接门店部门名称']
            existing_fill_cols = [col for col in fill_cols if col in new_df.columns]
            new_df[existing_fill_cols] = new_df[existing_fill_cols].ffill()
            
            new_df = new_df.dropna(subset=['商机开启专家姓名'])
            new_df['开启商机量'] = pd.to_numeric(new_df['开启商机量'], errors='coerce').fillna(0)
            new_df['加微开启商机量'] = pd.to_numeric(new_df['加微开启商机量'], errors='coerce').fillna(0)
            
            new_df['上传日期'] = new_df['上传日期'].astype(str)

            if not historical_df.empty:
                historical_df['上传日期'] = historical_df['上传日期'].astype(str)
                combined_df = pd.concat([historical_df, new_df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['上传日期', '商机首次承接门店部门名称', '商机开启专家姓名'], keep='last')
            else:
                combined_df = new_df

            with st.spinner('正在将数据永久归档至 GitHub 仓库...'):
                csv_content = combined_df.to_csv(index=False).encode('utf-8-sig')
                encoded_content = base64.b64encode(csv_content).decode('utf-8')
                
                payload = {
                    "message": "Auto-update historical data via Streamlit",
                    "content": encoded_content
                }
                if file_sha: 
                    payload["sha"] = file_sha
                    
                push_res = requests.put(API_URL, headers=HEADERS, json=payload)
                
                if push_res.status_code in [200, 201]:
                    historical_df = combined_df 
                    st.cache_data.clear()       
                    st.success("✅ 数据已成功分析，并作为文件永久保存在你的 GitHub 仓库中！")
                else:
                    st.error(f"❌ 数据同步云端失败！错误码: {push_res.status_code}，详情: {push_res.text}")
elif admin_pw != "":
    st.error("❌ 密码错误，无法开启上传功能。")

# ======================
# 📊 公开展示：数据可视化与双频道布局
# ======================
if not historical_df.empty:
    historical_df['上传日期'] = historical_df['上传日期'].astype(str)
    
    st.divider()
    
    store_col = '商机首次承接门店部门名称'
    if store_col not in historical_df.columns:
        store_col = '商机开启专家所属门店' if '商机开启专家所属门店' in historical_df.columns else None

    if store_col:
        store_daily = historical_df.groupby(['上传日期', store_col])[['加微开启商机量', '开启商机量']].sum().reset_index()
        store_daily['门店加微率'] = store_daily['加微开启商机量'] / store_daily['开启商机量']
        store_daily['门店加微率'] = store_daily['门店加微率'].fillna(0)
        store_daily = store_daily.sort_values(by='上传日期')

        tab1, tab2 = st.tabs(["📊 频道一：整体历史趋势", "🚨 频道二：今日异常监控 (紧凑平铺版)"])

        # ==========================================
        # 频道 1：保留完整历史大盘
        # ==========================================
        with tab1:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.header("🏢 所有门店开启商机加微率大盘")
            with col2:
                st.write("") 
                csv_store = store_daily.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 下载门店清洗汇总数据",
                    data=csv_store,
                    file_name="所有门店加微率_清洗数据.csv",
                    mime="text/csv",
                    use_container_width=True
                )

            fig_store = px.line(store_daily, x='上传日期', y='门店加微率', color=store_col, markers=True, text='门店加微率')
            fig_store.update_traces(texttemplate='%{text:.1%}', textposition="bottom right", hovertemplate='%{y:.1%}')
            fig_store.update_layout(yaxis_tickformat='.0%', hovermode='x unified')
            st.plotly_chart(fig_store, use_container_width=True)

        # ==========================================
        # 频道 2：“双列紧凑展示”最新一日数据并标红预警
        # ==========================================
        with tab2:
            latest_date_overall = historical_df['上传日期'].max()
            
            st.header(f"📋 【{latest_date_overall}】所有门店数据总表")
            
            latest_store_df = store_daily[store_daily['上传日期'] == latest_date_overall].copy()
            latest_store_df = latest_store_df.sort_values(by='门店加微率', ascending=False)
            
            styler_store = latest_store_df.style.map(
                color_red_if_low, subset=['门店加微率']
            ).format({'门店加微率': '{:.1%}'})
            
            st.table(styler_store)
            
            st.divider()
            
            st.header(f"🧑‍💼 【{latest_date_overall}】各门店专家业绩追踪雷达")
            st.markdown("🎯 **电梯直达：点击门店名称快速跳转至对应区域**")
            
            all_stores_raw = sorted(historical_df[store_col].dropna().unique().tolist())
            
            valid_stores = []
            toc_links = []
            for store in all_stores_raw:
                if not historical_df[(historical_df[store_col] == store) & (historical_df['上传日期'] == latest_date_overall)].empty:
                    valid_stores.append(store)
                    link_html = f'<a href="#{store}" style="display:inline-block; margin:5px; padding:6px 16px; background-color:#e0e5ec; border-radius:20px; text-decoration:none; color:#1f1f1f; font-weight:500; font-size:14px; box-shadow: 1px 1px 3px rgba(0,0,0,0.1);">{store}</a>'
                    toc_links.append(link_html)
            
            st.markdown(f"<div style='margin-bottom: 30px;'>{''.join(toc_links)}</div>", unsafe_allow_html=True)

            for i in range(0, len(valid_stores), 2):
                cols = st.columns(2)
                
                for j in range(2):
                    if i + j < len(valid_stores):
                        store = valid_stores[i + j]
                        
                        with cols[j]:
                            st.markdown(f'<div id="{store}"></div>', unsafe_allow_html=True)
                            st.subheader(f"📍 【{store}】")
                            
                            latest_expert_raw = historical_df[(historical_df[store_col] == store) & (historical_df['上传日期'] == latest_date_overall)].copy()
                            expert_latest = latest_expert_raw.groupby(['商机开启专家姓名'])[['加微开启商机量', '开启商机量']].sum().reset_index()
                            expert_latest['专家加微率'] = expert_latest['加微开启商机量'] / expert_latest['开启商机量']
                            expert_latest['专家加微率'] = expert_latest['专家加微率'].fillna(0)

                            # 加入 config 参数：隐藏画图工具自带的悬浮菜单栏，保证截图更纯净
                            fig_dual = make_subplots(specs=[[{"secondary_y": True}]])
                            fig_dual.add_trace(go.Bar(x=expert_latest['商机开启专家姓名'], y=expert_latest['开启商机量'], name="开启量", text=expert_latest['开启商机量'], textposition='auto'), secondary_y=False)
                            fig_dual.add_trace(go.Bar(x=expert_latest['商机开启专家姓名'], y=expert_latest['加微开启商机量'], name="加微量", text=expert_latest['加微开启商机量'], textposition='auto'), secondary_y=False)
                            fig_dual.add_trace(go.Scatter(x=expert_latest['商机开启专家姓名'], y=expert_latest['专家加微率'], name="加微率", mode="lines+markers+text", text=expert_latest['专家加微率'].apply(lambda x: f"{x:.1%}"), textposition="top center", marker=dict(size=8, color='red'), line=dict(color='red', width=3)), secondary_y=True)
                            
                            fig_dual.update_layout(barmode='group', hovermode='x unified', legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1), margin=dict(l=0, r=0, t=30, b=0))
                            fig_dual.update_yaxes(title_text="单量", secondary_y=False)
                            fig_dual.update_yaxes(title_text="率", tickformat=".0%", secondary_y=True)
                            st.plotly_chart(fig_dual, use_container_width=True, config={'displayModeBar': False})

                            styler_expert = expert_latest.style.map(
                                color_red_if_low, subset=['专家加微率']
                            ).format({'专家加微率': '{:.1%}'})
                            
                            st.table(styler_expert)
                
                st.markdown("---")

    with st.expander("📂 点击获取底层全量历史数据打包"):
        csv_data = historical_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(label="📥 一键下载所有原始数据 (CSV)", data=csv_data, file_name="全量历史明细.csv", mime="text/csv")
else:
    st.info("💡 云端数据库目前为空，请管理员输入密码并上传数据报表以初始化数据库。")
