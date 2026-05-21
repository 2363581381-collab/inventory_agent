import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from io import BytesIO
import datetime

st.set_page_config(page_title="库存补货智能体", layout="wide")
st.title("库存补货辅助决策智能体")
st.markdown("基于ABC分类、需求频率、服务水平98%的安全库存计算，推荐订货策略")

with st.sidebar:
    st.header("库存管理知识库")
    with st.expander("什么是ABC分类法？"):
        st.write("A类高价值，重点管理；B类中等；C类低价值，简化管理。")
    with st.expander("什么是安全库存？"):
        st.write("安全库存 = Z * 标准差 * sqrt(提前期)，Z取决于服务水平。")
    with st.expander("什么是再订货点（ROP）？"):
        st.write("ROP = 日均需求 * 提前期 + 安全库存")
    with st.expander("三种订货模式的区别？"):
        st.write("A类→不定期不定量，B类→定期不定量，C类→定期定量")

st.subheader("1. 输入数据")
uploaded_file = st.file_uploader("上传Excel文件（包含历史需求和库存数据）", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.success("数据加载成功！")
    st.dataframe(df)
else:
    st.info("使用示例数据，您可以上传自己的Excel。")
    data = {
        "仓库": ["华东仓库", "华东仓库", "华中仓库", "华中仓库", "华北仓库", "华北仓库",
                 "华南仓库", "华南仓库", "西南仓库", "西南仓库", "总仓库", "总仓库"],
        "品类": ["饮用水", "碳酸饮料", "饮用水", "碳酸饮料", "饮用水", "碳酸饮料",
                 "饮用水", "碳酸饮料", "饮用水", "碳酸饮料", "饮用水", "碳酸饮料"],
        "SKU": ["A型500ml"] * 12,
        "单价(元/箱)": [20, 50, 20, 50, 20, 50, 20, 50, 20, 50, 20, 50],
        "第10月需求(箱)": [17338, 17774, 9802, 11457, 45300, 8254, 15209, 6273, 1963, 2946, 481702, 255166],
        "第11月需求(箱)": [19666, 17186, 36755, 12204, 18125, 9107, 24340, 5983, 1931, 1531, 481702, 255166],
        "第12月需求(箱)": [21275, 17032, 19760, 11752, 40850, 8363, 17844, 6951, 12912, 5711, 481702, 255166],
        "库存量(箱)": [50000] * 12,
        "提前期(天)": [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 7, 7]
    }
    df = pd.DataFrame(data)
    st.dataframe(df)

st.subheader("2. 参数设置")
col1, col2, col3 = st.columns(3)
with col1:
    service_level = st.slider("服务水平目标", 0.90, 0.99, 0.98, 0.01)
    z_dict = {0.90:1.28, 0.95:1.645, 0.98:2.05, 0.99:2.33}
    Z = z_dict[service_level]
with col2:
    ordering_cost = st.number_input("每次订货成本（元）", value=5000, step=500)
with col3:
    holding_rate = st.number_input("年持有成本率（%）", value=10.08, step=0.5) / 100

def abc_classification(df_value_col):
    total = df_value_col.sum()
    df_sorted = df_value_col.sort_values(ascending=False)
    cum_perc = df_sorted.cumsum() / total
    abc = []
    for p in cum_perc:
        if p <= 0.7:
            abc.append("A")
        elif p <= 0.9:
            abc.append("B")
        else:
            abc.append("C")
    return pd.Series(abc, index=df_value_col.index)

def calculate_safety_stock(std_monthly, lead_time_days, Z):
    L_month = lead_time_days / 28
    return Z * std_monthly * (L_month ** 0.5)

def eoq(annual_demand, ordering_cost, holding_cost_per_unit):
    if holding_cost_per_unit <= 0:
        return 0
    return np.sqrt(2 * annual_demand * ordering_cost / holding_cost_per_unit)

def recommend_mode(abc_class, demand_freq):
    if abc_class == "A":
        return "不定期不定量"
    elif abc_class == "B":
        return "定期不定量"
    else:
        return "定期定量"

st.subheader("3. 计算结果（决策表）")
df_decision = df.copy()

demand_cols = ["第10月需求(箱)", "第11月需求(箱)", "第12月需求(箱)"]
df_decision["月需求标准差"] = df_decision[demand_cols].std(axis=1, ddof=1).fillna(0)
df_decision["安全库存(箱)"] = df_decision.apply(
    lambda row: calculate_safety_stock(row["月需求标准差"], row["提前期(天)"], Z), axis=1
)
df_decision["日平均需求(箱)"] = df_decision["第12月需求(箱)"] / 28
df_decision["库存总价值"] = df_decision["库存量(箱)"] * df_decision["单价(元/箱)"]
df_decision["ABC分类"] = abc_classification(df_decision["库存总价值"])

def demand_freq_level(demand):
    if demand > 30000: return 12
    elif demand > 20000: return 10
    elif demand > 10000: return 8
    elif demand > 5000: return 5
    else: return 3
df_decision["需求频率"] = df_decision["第12月需求(箱)"].apply(demand_freq_level)
df_decision["分类标签"] = df_decision["ABC分类"] + df_decision["需求频率"].astype(str)
df_decision["推荐订货模式"] = df_decision.apply(lambda row: recommend_mode(row["ABC分类"], row["需求频率"]), axis=1)

def calc_rop(row):
    if row["推荐订货模式"] == "不定期不定量":
        return row["安全库存(箱)"] + row["日平均需求(箱)"] * row["提前期(天)"]
    else:
        return None
df_decision["再订货点(箱)"] = df_decision.apply(calc_rop, axis=1)

def calc_max_stock(row):
    if row["推荐订货模式"] == "定期不定量":
        T = 7
        return row["安全库存(箱)"] + (T + row["提前期(天)"]) * row["日平均需求(箱)"]
    else:
        return None
df_decision["最高库存(箱)"] = df_decision.apply(calc_max_stock, axis=1)
df_decision["订货间隔(天)"] = df_decision["推荐订货模式"].apply(lambda x: 7 if x == "定期不定量" else None)

def adjust_max_stock(row):
    if pd.notna(row["最高库存(箱)"]) and row["最高库存(箱)"] > 250000:
        row["推荐订货模式"] = "不定期不定量"
        row["订货间隔(天)"] = None
        row["再订货点(箱)"] = row["安全库存(箱)"] + row["日平均需求(箱)"] * row["提前期(天)"]
        row["最高库存(箱)"] = 250000
        if row["再订货点(箱)"] >= row["最高库存(箱)"]:
            row["再订货点(箱)"] = row["最高库存(箱)"] * 0.9
    return row
df_decision = df_decision.apply(adjust_max_stock, axis=1)

df_decision["年需求预测"] = df_decision["第12月需求(箱)"] * 12
df_decision["单位年持有成本"] = df_decision["单价(元/箱)"] * holding_rate
df_decision["EOQ(箱)"] = df_decision.apply(lambda row: eoq(row["年需求预测"], ordering_cost, row["单位年持有成本"]), axis=1)

display_cols = ["仓库", "品类", "SKU", "ABC分类", "需求频率", "分类标签", "推荐订货模式",
                "安全库存(箱)", "再订货点(箱)", "订货间隔(天)", "最高库存(箱)", "EOQ(箱)", "库存量(箱)"]
result_df = df_decision[display_cols].round(0)
st.dataframe(result_df)

st.subheader("4. 可视化分析")
tab1, tab2, tab3 = st.tabs(["安全库存对比", "需求趋势", "库存监控"])
with tab1:
    fig = px.bar(result_df, x="分类标签", y="安全库存(箱)", color="仓库", title="各SKU安全库存")
    st.plotly_chart(fig, use_container_width=True)
with tab2:
    demand_trend = df_decision.melt(id_vars=["分类标签"], value_vars=demand_cols, var_name="月份", value_name="需求(箱)")
    fig2 = px.line(demand_trend, x="月份", y="需求(箱)", color="分类标签", title="历史需求趋势")
    st.plotly_chart(fig2, use_container_width=True)
with tab3:
    monitor = result_df[result_df["推荐订货模式"] == "不定期不定量"].copy()
    if not monitor.empty:
        monitor["当前库存(箱)"] = monitor["库存量(箱)"]
        fig3 = px.bar(monitor, x="分类标签", y=["当前库存(箱)", "再订货点(箱)"], barmode="group", title="重点SKU监控")
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("没有需要不定期不定量管理的SKU。")

st.subheader("5. 导出决策表")
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="补货决策")
    return output.getvalue()
excel_data = to_excel(result_df)
st.download_button("下载决策表 (Excel)", data=excel_data, file_name="inventory_decision.xlsx")
st.markdown(f"*最后更新：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")