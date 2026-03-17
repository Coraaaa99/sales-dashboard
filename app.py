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
st.markdown("每日上传数据自动进行云端汇总。团队成员可查看趋势并下载全量历史数据。")

# ======================
# GitHub API 数据库配置
# ======================
try:
    GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    GITHUB_REPO = st.secrets["GITHUB_REPO"]
    FILE_PATH = "historical_data.csv" # 在你的代码仓库里自动建这个文件
    API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"
    HEADERS = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
except Exception:
    st.error("⚠️ 未在 Streamlit Secrets 中找到 GitHub 密钥配置，请检查。")
    st.stop()

# 1. 启动时从 GitHub 仓库获取历史数据
@st.cache_data(ttl=60) # 缓存60秒避免频繁请求
def load_historical_data():
    try:
        res = requests.get(API_URL, headers=HEADERS)
        if res.status_code == 200:
            data = res.json()
            # GitHub 存的文件是 base64 编码的，需要解码
            content = base64.b64decode(data['content']).decode('utf-8-sig')
            df = pd.read_csv(io.StringIO(content))
            return df, data['sha'] # 返回数据和文件的唯一标识符(更新时必须用)
        elif res.status_code == 404:
            # 404代表文件还不存在（第一次运行），这是正常的
            return pd.DataFrame(), None 
    except Exception as e:
        st.error(f"读取云端历史数据失败: {e}")
    return pd.DataFrame(), None

historical_df, file_sha = load_historical_data()

# ======================
# 新数据上传与合并
# ======================
uploaded_files = st.file_uploader("📤 请上传当天的 Excel/CSV 数据报表（以日期命名，如 2023-10-16.xlsx）", accept_multiple_files=True)

if uploaded_files:
    new_data = []
    for file in uploaded_files:
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            # 提取文件名作为日期，并强制转换为纯文本字符串
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
        
        # 强制把新数据的日期列转为字符串
        new_df['上传日期'] = new_df['上传日期'].astype(str)

        # 与历史数据合并去重
        if not historical_df.empty:
            # 同样强制老数据的日期列为字符串，防止拼接时类型不一
            historical_df['上传日期'] = historical_df['上传日期'].astype(str)
            combined_df = pd.concat([historical_df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['上传日期', '商机开启专家工号'], keep='last')
        else:
            combined_df = new_df

        # ======================
        # 推送最新数据到 GitHub 仓库保存
        # ======================
        with st.spinner('正在将数据永久归档至 GitHub 仓库...'):
            # 将表格转为带防乱码的 csv 文本格式
            csv_content = combined_df.to_csv(index=False).encode('utf-8-sig')
            encoded_content = base64.b64encode(csv_content).decode('utf-8')
            
            payload = {
                "message": "Auto-update historical data via Streamlit",
                "content": encoded_content
            }
            if file_sha: # 如果原来有文件，更新它必须带上原本的 sha 码
                payload["sha"] = file_sha
                
            push_res = requests.put(API_URL, headers=HEADERS, json=payload)
            
            if push_res.status_code in [200, 201]:
                historical_df = combined_df # 更新内存数据用于立即展示
                st.cache_data.clear()       # 清除旧缓存
                st.success("✅ 数据已成功分析，并作为文件永久保存在你的 GitHub 仓库中！")
            else:
                st.error(f"❌ 数据同步云端失败！错误码: {push_res.status_code}，详情: {push_res.text}")

# ======================
# 数据可视化与下载功能
# ======================
if not historical_df.empty:
    # 🌟 终极防御：在画图和排队前，确保当前要处理的数据日期全都是纯文本
    historical_df['上传日期'] = historical_df['上传日期'].astype(str)
    
    st.divider()
    
    csv_data = historical_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下载云端完整历史数据明细 (CSV格式)",
        data=csv_data,
        file_name="业务加微率_历史汇总明细.csv",
        mime="text/csv",
        type="primary"
    )
    
    st.header("🏢 每个门店的开启商机加微率")
    store_daily = historical_df.groupby(['上传日期', '商机开启专家所属门店'])[['加微开启商机量', '开启商机量']].sum().reset_index()
    store_daily['门店加微率'] = store_daily['加微开启商机量'] / store_daily['开启商机量']
    store_daily['门店加微率'] = store_daily['门店加微率'].fillna(0)
    
    # 因为日期已经是统一的文本了，这里排序绝对不会再报错！
    store_daily = store_daily.sort_values(by='上传日期')

    fig_store = px.line(store_daily, x='上传日期', y='门店加微率', color='商机开启专家所属门店', markers=True, text='门店加微率')
    fig_store.update_traces(texttemplate='%{text:.1%}', textposition="bottom right")
    fig_store.update_layout(yaxis_tickformat='.0%')
    st.plotly_chart(fig_store, use_container_width=True)

    st.divider()
    st.header("🧑‍💼 专家开启商机加微率日度趋势")
    all_stores = sorted(historical_df['商机开启专家所属门店'].unique().tolist())
    selected_store = st.selectbox("请选择要查看的具体门店进行深入分析", options=all_stores)
    
    if selected_store:
        store_experts_df = historical_df[historical_df['商机开启专家所属门店'] == selected_store].copy()
        expert_daily = store_experts_df.groupby(['上传日期', '商机开启专家姓名'])[['加微开启商机量', '开启商机量']].sum().reset_index()
        expert_daily['专家加微率'] = expert_daily['加微开启商机量'] / expert_daily['开启商机量']
        expert_daily['专家加微率'] = expert_daily['专家加微率'].fillna(0)
        
        # 同样安全排序
        expert_daily = expert_daily.sort_values(by='上传日期')

        fig_expert = px.line(expert_daily, x='上传日期', y='专家加微率', color='商机开启专家姓名', markers=True)
        fig_expert.update_layout(yaxis_tickformat='.0%')
        st.plotly_chart(fig_expert, use_container_width=True)
else:
    st.info("💡 云端数据库目前为空，请管理员在上方上传今日的报表文件。")
