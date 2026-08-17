"""
树剪可视化看板 v3.0 - 全功能Streamlit面板
六大页面：概览/队列/质检/素材/配置/监控
"""
import os
import sys
import time
from datetime import datetime
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)
import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import psutil
st.set_page_config(
    page_title="树剪 v3.0 监控看板",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)
DB_PATH = os.path.join(PROJECT_ROOT, "data", "db", "system.db")
st.markdown("""
<style>
    .stMetric { background: #f0f2f6; padding: 15px; border-radius: 8px; }
    .stApp { background-color: #f8f9fa; }
</style>
""", unsafe_allow_html=True)
@st.cache_data(ttl=5)
def load_data(sql, params=()):
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(sql, conn, params=params)
        conn.close()
        return df
    except Exception:
        return pd.DataFrame()
def load_scalar(sql, params=(), default=0):
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(sql, params).fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default
def get_system_status():
    status = {
        "cpu": psutil.cpu_percent(interval=0.3),
        "mem_percent": psutil.virtual_memory().percent,
        "mem_used": round(psutil.virtual_memory().used / 1024**3, 1),
        "mem_total": round(psutil.virtual_memory().total / 1024**3, 1),
    }
    try:
        from pynvml import nvmlInit, nvmlDeviceGetHandleByIndex, nvmlDeviceGetMemoryInfo
        from pynvml import nvmlDeviceGetUtilizationRates, nvmlDeviceGetTemperature, nvmlDeviceGetName
        from pynvml import nvmlShutdown, NVML_TEMPERATURE_GPU
        nvmlInit()
        h = nvmlDeviceGetHandleByIndex(0)
        mem = nvmlDeviceGetMemoryInfo(h)
        util = nvmlDeviceGetUtilizationRates(h)
        name = nvmlDeviceGetName(h)
        status["gpu_name"] = name.decode() if isinstance(name, bytes) else name
        status["vram_used"] = round(mem.used / 1024**2, 1)
        status["vram_total"] = round(mem.total / 1024**2, 1)
        status["gpu_util"] = util.gpu
        status["gpu_temp"] = nvmlDeviceGetTemperature(h, NVML_TEMPERATURE_GPU)
        nvmlShutdown()
    except Exception:
        status["gpu_name"] = "未检测到"
        status["vram_used"] = 0
        status["vram_total"] = 6144
        status["gpu_util"] = 0
        status["gpu_temp"] = 0
    return status
# 侧边栏
with st.sidebar:
    st.title("🎬 树剪控制台")
    page = st.radio("导航", [
        "📊 运行概览", "📋 任务队列", "🔍 质检中心",
        "📁 素材库", "⚙️ 系统配置", "💻 硬件监控",
    ])
    st.divider()
    st.caption(f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if st.button("🔄 刷新缓存"):
        st.cache_data.clear()
        st.rerun()
# ====== 运行概览 ======
if page == "📊 运行概览":
    st.header("📊 运行概览")
    tasks_df = load_data("SELECT * FROM tasks ORDER BY create_time DESC")
    materials_df = load_data("SELECT * FROM materials")
    quality_df = load_data("SELECT * FROM quality_results")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("素材总数", len(materials_df))
    c2.metric("总任务数", len(tasks_df))
    c3.metric("已完成", len(tasks_df[tasks_df["status"] == "completed"]) if not tasks_df.empty else 0)
    c4.metric("质检问题", len(quality_df))
    st.subheader("最近任务")
    if not tasks_df.empty:
        st.dataframe(tasks_df.head(10), use_container_width=True, hide_index=True)
    else:
        st.info("暂无任务")
# ====== 任务队列 ======
elif page == "📋 任务队列":
    st.header("📋 任务队列管理")
    col1, col2 = st.columns(2)
    with col1:
        uploaded = st.file_uploader("上传素材", type=["mp4", "mov", "avi"], accept_multiple_files=True)
        if uploaded:
            for f in uploaded:
                save_path = os.path.join(PROJECT_ROOT, "data", "materials", f.name)
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as out:
                    out.write(f.read())
                st.success(f"已添加: {f.name}")
    with col2:
        folder_path = st.text_input("文件夹路径（批量导入）")
        if st.button("开始导入") and folder_path:
            from tasks.task_queue import task_queue
            count = task_queue.add_folder(folder_path)
            st.success(f"导入完成，共{count}个")
    st.divider()
    queue_df = load_data(
        """SELECT q.id, m.file_path, q.status, q.priority, q.create_time
           FROM task_queue q JOIN materials m ON q.material_id=m.id ORDER BY q.id DESC"""
    )
    if not queue_df.empty:
        st.dataframe(queue_df, use_container_width=True, hide_index=True)
    if st.button("▶️ 运行全部等待任务", type="primary"):
        from tasks.task_queue import task_queue
        total = task_queue.run_all()
        st.success(f"批量完成，共{total}个")
# ====== 质检中心 ======
elif page == "🔍 质检中心":
    st.header("🔍 质检结果中心")
    qdf = load_data("SELECT * FROM quality_results ORDER BY check_time DESC")
    if qdf.empty:
        st.info("暂无质检数据")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("总问题", len(qdf))
        c2.metric("已修复", len(qdf[qdf["is_fixed"] == 1]))
        c3.metric("待处理", len(qdf[qdf["is_fixed"] == 0]))
        col1, col2 = st.columns(2)
        with col1:
            tc = qdf["check_type"].value_counts().reset_index()
            tc.columns = ["类型", "数量"]
            fig = px.pie(tc, values="数量", names="类型", hole=0.3, title="问题类型")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            lc = qdf["issue_level"].value_counts().reset_index()
            lc.columns = ["等级", "数量"]
            fig = px.bar(lc, x="等级", y="数量", color="等级", title="问题等级")
            st.plotly_chart(fig, use_container_width=True)
        st.subheader("质检详情")
        st.dataframe(qdf, use_container_width=True, hide_index=True)
        csv = qdf.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 导出CSV", csv, "质检报告.csv", "text/csv")
# ====== 素材库 ======
elif page == "📁 素材库":
    st.header("📁 素材资源库")
    mdf = load_data(
        """SELECT id, file_path, status, duration, resolution, fps, version, create_time
           FROM materials ORDER BY create_time DESC"""
    )
    if not mdf.empty:
        sf = st.multiselect("状态", ["pending", "processed", "failed"], default=["pending", "processed"])
        filtered = mdf[mdf["status"].isin(sf)]
        st.dataframe(filtered, use_container_width=True, hide_index=True)
    else:
        st.info("暂无素材")
# ====== 系统配置 ======
elif page == "⚙️ 系统配置":
    st.header("⚙️ 系统配置")
    config_path = os.path.join(PROJECT_ROOT, "config", "system_config.yaml")
    st.info("热修改功能开发中，可直接编辑 config/system_config.yaml")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            st.code(f.read(), language="yaml")
# ====== 硬件监控 ======
elif page == "💻 硬件监控":
    st.header("💻 硬件实时监控")
    s = get_system_status()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CPU", f"{s['cpu']}%")
    c2.metric("内存", f"{s['mem_percent']}%", f"{s['mem_used']}/{s['mem_total']}GB")
    c3.metric("GPU", f"{s['gpu_util']}%")
    c4.metric("显存", f"{s['vram_used']}/{s['vram_total']}MB")
    col1, col2 = st.columns(2)
    col1.metric("GPU温度", f"{s['gpu_temp']}°C")
    col2.metric("显卡型号", s["gpu_name"])
    st.caption("每5秒自动刷新")
    time.sleep(5)
    st.rerun()
st.divider()
st.caption(f"树剪 AI智能生产系统 v3.0 | DB: {DB_PATH}")
