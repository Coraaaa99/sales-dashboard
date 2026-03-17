import streamlit as st
import pandas as pd
import plotly.express as px
import os
import requests
import json

# 设置网页基本配置
st.set_page_config(page_title="商机加微率每日分析", layout="wide")
st.title("📈 门店与专家商机加微率分析看板")
st.markdown("每日上传数据自动进行云端汇总。团队成员可查看趋势并下载全量历史数据。")

# ======================
# 云端 API 存储配置
# ======================
try:
    BIN_ID = st.secrets["JSONBIN_BIN_ID"]
    API_KEY = st.secrets["JSONBIN_API_KEY"]
    API_URL = f"https://api.jsonbin.io/v3/b/{BIN_ID}"
except Exception:
    st.error("⚠️ 未在 Streamlit Secrets 中找到云端数据库密钥，请检查配置。")
    st.stop()

# 定义请求头
HEADERS_READ = {
    'X-Master-Key': API_KEY
}
HEADERS_WRITE = {
    'Content-Type': 'application/json',
    'X-Master-Key': API_KEY
}

# 1. 启动时从云端 API 获取历史数据
@st.cache_data(ttl=60) # 缓存60秒避免频繁请求
def load_historical_data():
    try:
        response = requests.get(API_URL, headers=HEADERS_READ)
        if response.status_code == 200:
            records = response.json().get('record', [])
            if records:
                return pd.DataFrame(records)
    except Exception as e:
        st.error(f"读取云端数据失败: {e}")
    return pd.DataFrame()

historical_df = load_historical_data()

# ======================
# 新数据上传与合并
# ======================
uploaded_files = st.file_uploader("📤 请上传当天的 Excel/CSV 数据报表（以日期命名，如 10月16日.xlsx）", accept_multiple_files=True)

if uploaded_files:
    new_data = []
    for file in uploaded_files:
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            date_str = os.path.splitext(file.name)[0]
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

        # 与历史数据合并去重
        if not historical_df.empty:
            combined_df = pd.concat([historical_df, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['上传日期', '商机开启专家工号'], keep='last')
        else:
            combined_df = new_df

        # 转换为 JSON 并推送到云端 API
        with st.spinner('正在同步数据到云端数据库...'):
            data_json = combined_df.to_json(orient='records')
            push_res = requests.put(API_URL, json=json.loads(data_json), headers=HEADERS_WRITE)
            
           if push_res.status_code == 200:
                historical_df = combined_df # 更新内存数据用于立即展示
                st.cache_data.clear()       # 清除旧缓存
                st.success("✅ 数据已成功分析并持久化存储至云端数据库！")
            else:
                st.error(f"❌ 数据同步云端失败！错误码: {push_res.status_code}，详情: {push_res.text}")
# ======================
# 数据可视化与下载功能
# ======================
if not historical_df.empty:
    st.divider()
    
    # 🌟 新增：全局明细数据下载按钮
    # 注意：使用 utf-8-sig 编码，确保导出的 CSV 在 Windows Excel 中打开不会中文乱码
    csv_data = historical_df.to_csv(index=False).encode('utf-8-sig')
    st.download_button(
        label="📥 下载云端完整历史数据明细 (CSV格式)",
        data=csv_data,
        file_name="业务加微率_历史汇总明细.csv",
        mime="text/csv",
        type="primary"
    )
    
    # 图表绘制模块
    st.header("🏢 每个门店的开启商机加微率")
    store_daily = historical_df.groupby(['上传日期', '商机开启专家所属门店'])[['加微开启商机量', '开启商机量']].sum().reset_index()
    store_daily['门店加微率'] = store_daily['加微开启商机量'] / store_daily['开启商机量']
    store_daily['门店加微率'] = store_daily['门店加微率'].fillna(0)
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
        expert_daily = expert_daily.sort_values(by='上传日期')

        fig_expert = px.line(expert_daily, x='上传日期', y='专家加微率', color='商机开启专家姓名', markers=True)
        fig_expert.update_layout(yaxis_tickformat='.0%')
        st.plotly_chart(fig_expert, use_container_width=True)
else:
    st.info("💡 云端数据库目前为空，请管理员在上方上传今日的报表文件。")
