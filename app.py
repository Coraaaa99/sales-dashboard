import streamlit as st
import pandas as pd
import plotly.express as px
import os
import requests
import base64
import io

# 设置网页基本配置
st.set_page_config(page_title="商机加微率每日分析", layout="wide")
st.title("📈 门店与专家商机加微率分析看板")
st.markdown("团队成员可随时查看趋势并下载历史数据。仅管理员可上传更新数据。")

# ======================
# GitHub API 数据库与密码配置
# ======================
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
    # 获取保险箱里的密码，如果没有设置，默认临时用 8888
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

# ======================
# 🔒 管理员专属：新数据上传与合并
# ======================
st.divider()
st.subheader("🔒 管理员数据上传区")
# 增加一个密码输入框
admin_pw = st.text_input("请输入管理员密码以开启上传功能：", type="password")

# 只有密码输入正确，才会显示上传框和后续处理逻辑
if admin_pw == ADMIN_PASSWORD:
    uploaded_files = st.file_uploader("📤 请上传当天的 Excel/CSV 数据报表（建议以日期命名，如 2023-10-16.xlsx）", accept_multiple_files=True)

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
            
            # 数据清洗处理
            new_df = new_df[new_df['商机开启专家所属大区'] != '合计']
            fill_cols = ['商机开启专家所属大区', '商机开启专家所属销售部', '商机开启归属经营单元部门名称', '商机开启专家所属门店']
            new_df[fill_cols] = new_df[fill_cols].ffill()
            new_df = new_df.dropna(subset=['商机开启专家姓名'])
            new_df['开启商机量'] = pd.to_numeric(new_df['开启商机量'], errors='coerce').fillna(0)
            new_df['加微开启商机量'] = pd.to_numeric(new_df['加微开启商机量'], errors='coerce').fillna(0)
            
            new_df['上传日期'] = new_df['上传日期'].astype(str)

            # 与历史数据合并去重
            if not historical_df.empty:
                historical_df['上传日期'] = historical_df['上传日期'].astype(str)
                combined_df = pd.concat([historical_df, new_df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['上传日期', '商机开启专家工号'], keep='last')
            else:
                combined_df = new_df

            # 推送最新数据到 GitHub 仓库保存
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
    # 如果输错了密码，给个红色提示
    st.error("❌ 密码错误，无法开启上传功能。")

# ======================
# 📊 公开展示：数据可视化与下载功能
# ======================
if not historical_df.empty:
    historical_df['上传日期'] = historical_df['上传日期'].astype(str)
    
    st.divider()
    
    with st.expander("📂 点击获取底层全量历史数据（未聚合）"):
        csv_data = historical_df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下载底层全量历史数据明细 (CSV格式)",
            data=csv_data,
            file_name="业务加微率_底层全量明细.csv",
            mime="text/csv"
        )
    
    # ----------------------------
    # 第一部分：门店趋势图及下载
    # ----------------------------
    store_daily = historical_df.groupby(['上传日期', '商机开启专家所属门店'])[['加微开启商机量', '开启商机量']].sum().reset_index()
    store_daily['门店加微率'] = store_daily['加微开启商机量'] / store_daily['开启商机量']
    store_daily['门店加微率'] = store_daily['门店加微率'].fillna(0)
    store_daily = store_daily.sort_values(by='上传日期')

    col1, col2 = st.columns([4, 1])
    with col1:
        st.header("🏢 每个门店的开启商机加微率")
    with col2:
        st.write("") 
        csv_store = store_daily.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下载门店清洗汇总数据",
            data=csv_store,
            file_name="分门店加微率_清洗数据.csv",
            mime="text/csv",
            use_container_width=True
        )

    fig_store = px.line(store_daily, x='上传日期', y='门店加微率', color='商机开启专家所属门店', markers=True, text='门店加微率')
    fig_store.update_traces(texttemplate='%{text:.1%}', textposition="bottom right")
    fig_store.update_layout(yaxis_tickformat='.0%')
    st.plotly_chart(fig_store, use_container_width=True)

    st.divider()
    
    # ----------------------------
    # 第二部分：专家趋势图及下载
    # ----------------------------
    all_stores = sorted(historical_df['商机开启专家所属门店'].unique().tolist())
    selected_store = st.selectbox("请选择要查看的具体门店进行深入分析", options=all_stores)
    
    if selected_store:
        store_experts_df = historical_df[historical_df['商机开启专家所属门店'] == selected_store].copy()
        expert_daily = store_experts_df.groupby(['上传日期', '商机开启专家姓名'])[['加微开启商机量', '开启商机量']].sum().reset_index()
        expert_daily['专家加微率'] = expert_daily['加微开启商机量'] / expert_daily['开启商机量']
        expert_daily['专家加微率'] = expert_daily['专家加微率'].fillna(0)
        expert_daily = expert_daily.sort_values(by='上传日期')

        col3, col4 = st.columns([4, 1])
        with col3:
            st.header(f"🧑‍💼 【{selected_store}】专家开启商机加微率")
        with col4:
            st.write("") 
            csv_expert = expert_daily.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label=f"📥 下载该门店专家数据",
                data=csv_expert,
                file_name=f"{selected_store}_专家加微率_清洗数据.csv",
                mime="text/csv",
                use_container_width=True
            )

        fig_expert = px.line(expert_daily, x='上传日期', y='专家加微率', color='商机开启专家姓名', markers=True, text='专家加微率')
        fig_expert.update_traces(texttemplate='%{text:.1%}', textposition="bottom right")
        fig_expert.update_layout(yaxis_tickformat='.0%')
        st.plotly_chart(fig_expert, use_container_width=True)

else:
    st.info("💡 云端数据库目前为空，请管理员输入密码并上传数据报表以初始化数据库。")
