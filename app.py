import streamlit as st
import pandas as pd
import plotly.express as px
import os

# 设置网页基本配置
st.set_page_config(page_title="商机加微率每日分析", layout="wide")
st.title("📈 门店与专家商机加微率分析看板")
st.markdown("每天上传当日的导出数据，自动生成各门店及专家的日度趋势图。")

# 1. 允许多文件上传（每天的数据作为一个独立文件）
uploaded_files = st.file_uploader("请上传每日导出的Excel或CSV文件（可一次性多选上传）", accept_multiple_files=True)

if uploaded_files:
    all_data = []
    
    for file in uploaded_files:
        # 根据文件扩展名读取数据
        try:
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
                
            # 从文件名中提取日期（假设你可以把文件命名为“2023-10-01.xlsx”等）
            date_str = os.path.splitext(file.name)[0]
            df['上传日期'] = date_str
            
            all_data.append(df)
        except Exception as e:
            st.error(f"读取文件 {file.name} 失败: {e}")

    if all_data:
        # 合并所有文件的数据
        full_df = pd.concat(all_data, ignore_index=True)
        
        # ======================
        # 数据清洗处理
        # ======================
        # 1. 剔除第一行可能包含的“合计”行
        full_df = full_df[full_df['商机开启专家所属大区'] != '合计']
        
        # 2. 解决合并单元格造成的空值问题：向下填充大区、销售部、门店等列
        fill_cols = ['商机开启专家所属大区', '商机开启专家所属销售部', '商机开启归属经营单元部门名称', '商机开启专家所属门店']
        # 注意：pandas 2.0+ 推荐使用 ffill()
        full_df[fill_cols] = full_df[fill_cols].ffill()
        
        # 3. 剔除没有专家的空行
        full_df = full_df.dropna(subset=['商机开启专家姓名'])
        
        # 4. 确保相关的指标列为数值格式
        full_df['开启商机量'] = pd.to_numeric(full_df['开启商机量'], errors='coerce').fillna(0)
        full_df['加微开启商机量'] = pd.to_numeric(full_df['加微开启商机量'], errors='coerce').fillna(0)
        
        st.divider()

        # ======================
        # 指标 2：每个门店的开启商机加微率趋势
        # ======================
        st.header("🏢 每个门店的开启商机加微率")
        st.markdown("**计算公式**: 门店加微率 = 门店所有专家加微量求和 / 门店所有专家开启量求和")
        
        # 按门店和日期进行汇总计算
        store_daily = full_df.groupby(['上传日期', '商机开启专家所属门店'])[['加微开启商机量', '开启商机量']].sum().reset_index()
        # 计算加微率
        store_daily['门店加微率'] = store_daily['加微开启商机量'] / store_daily['开启商机量']
        store_daily['门店加微率'] = store_daily['门店加微率'].fillna(0)
        
        # 绘制交互式折线图
        fig_store = px.line(store_daily, x='上传日期', y='门店加微率', color='商机开启专家所属门店', 
                            markers=True, text='门店加微率', title='各门店每日开启商机加微率趋势')
        fig_store.update_traces(texttemplate='%{text:.1%}', textposition="bottom right")
        fig_store.update_layout(yaxis_tickformat='.0%')
        st.plotly_chart(fig_store, use_container_width=True)
        
        # 展示数据明细
        with st.expander("点击查看门店汇总数据明细"):
            # 整理数据为更易读的百分比格式
            display_store = store_daily.copy()
            display_store['门店加微率'] = display_store['门店加微率'].apply(lambda x: f"{x:.2%}")
            st.dataframe(display_store, use_container_width=True)

        st.divider()

        # ======================
        # 指标 1：分门店每个专家开启商机加微率的日度趋势
        # ======================
        st.header("🧑‍💼 专家开启商机加微率日度趋势")
        
        # 增加交互组件：让用户选择具体要查看的门店
        all_stores = sorted(full_df['商机开启专家所属门店'].unique().tolist())
        selected_store = st.selectbox("请选择要查看的门店", options=all_stores)
        
        if selected_store:
            # 过滤出选中门店的专家数据
            store_experts_df = full_df[full_df['商机开启专家所属门店'] == selected_store].copy()
            
            # 汇总日度数据（防重名/冗余）
            expert_daily = store_experts_df.groupby(['上传日期', '商机开启专家姓名'])[['加微开启商机量', '开启商机量']].sum().reset_index()
            expert_daily['专家加微率'] = expert_daily['加微开启商机量'] / expert_daily['开启商机量']
            expert_daily['专家加微率'] = expert_daily['专家加微率'].fillna(0)
            
            # 绘制图表
            fig_expert = px.line(expert_daily, x='上传日期', y='专家加微率', color='商机开启专家姓名', 
                                 markers=True, title=f'【{selected_store}】专家每日开启商机加微率趋势')
            fig_expert.update_layout(yaxis_tickformat='.0%')
            st.plotly_chart(fig_expert, use_container_width=True)
            
            # 展示专家数据明细
            with st.expander(f"点击查看【{selected_store}】专家明细数据"):
                display_expert = expert_daily.copy()
                display_expert['专家加微率'] = display_expert['专家加微率'].apply(lambda x: f"{x:.2%}")
                st.dataframe(display_expert, use_container_width=True)
else:
    st.info("💡 请在上方上传数据文件以生成可视化报表。为了能够识别日期，建议将每天导出的文件名命名为当天的日期，例如 `2023-10-01.xlsx`、`2023-10-02.csv`")