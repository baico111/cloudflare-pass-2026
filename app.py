import streamlit as st
import json
import os
import subprocess
from datetime import datetime, timedelta

# 配置文件存放在持久化目录
CONFIG_FILE = "/app/output/tasks_config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return [{"name": "Katabump续期", "script": "katabump_renew.py", "mode": "单浏览器模式", "email": "", "password": "", "freq": 3, "active": True, "last_run": None}]

def save_config(tasks):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

st.set_page_config(page_title="自动化任务管理器", layout="wide")
st.title("🤖 多项目自动化续期管理中心")

if 'tasks' not in st.session_state:
    st.session_state.tasks = load_config()

# --- 侧边栏保持不变 ---
with st.sidebar:
    st.header("➕ 添加新项目")
    new_name = st.text_input("项目备注名称")
    available_scripts = ["katabump_renew.py", "bypass.py", "bypass_seleniumbase.py", "simple_bypass.py"]
    new_script = st.selectbox("关联脚本文件", available_scripts)
    if st.button("添加至列表"):
        st.session_state.tasks.append({
            "name": new_name, "script": new_script, 
            "mode": "单浏览器模式", "email": "", "password": "", "freq": 3, "active": True, "last_run": None
        })
        save_config(st.session_state.tasks)
        st.success("已添加！")

# --- 主界面：配置区 ---
updated_tasks = []
st.subheader("📋 任务列表 (配置自动保存)")

for i, task in enumerate(st.session_state.tasks):
    with st.expander(f"项目: {task['name']} (脚本: {task['script']})", expanded=True):
        col1, col2, col3, col4, col5, col6 = st.columns([0.8, 1.2, 1.5, 1.5, 1, 0.5])
        
        task['active'] = col1.checkbox("启用", value=task.get('active', True), key=f"active_{i}")
        
        mode_options = ["单浏览器模式", "SB增强模式", "并行竞争模式"]
        current_mode = task.get('mode', "单浏览器模式")
        default_idx = mode_options.index(current_mode) if current_mode in mode_options else 0
        task['mode'] = col2.selectbox("验证模式", mode_options, index=default_idx, key=f"mode_{i}")
        
        task['email'] = col3.text_input("账号", value=task.get('email', ''), key=f"email_{i}")
        task['password'] = col4.text_input("密码", type="password", value=task.get('password', ''), key=f"pw_{i}")
        
        # --- 解决问题一：增加执行频率(天)的选择 ---
        task['freq'] = col5.number_input("间隔(天)", min_value=1, max_value=30, value=task.get('freq', 3), key=f"freq_{i}")

        if col6.button("🗑️", key=f"del_{i}"):
            st.session_state.tasks.pop(i)
            save_config(st.session_state.tasks)
            st.rerun()
        
        # 显示上次执行时间和预计下次执行时间
        last_run = task.get('last_run')
        if last_run:
            next_run = (datetime.strptime(last_run, "%Y-%m-%d %H:%M:%S") + timedelta(days=task['freq'])).strftime("%Y-%m-%d")
            st.caption(f"📅 上次运行: {last_run} | ⏳ 预计下次自动续期: {next_run}")
        else:
            st.caption("📅 上次运行: 从未执行 | ⏳ 状态: 待触发")

        updated_tasks.append(task)

if st.button("💾 保存所有配置"):
    save_config(updated_tasks)
    st.success("✅ 配置已保存！")

st.divider()

# --- 解决问题二：手动执行区（优化实时日志输出） ---
if st.button("🚀 统一点执行 (一键跑通)"):
    # 在按钮下方创建一个容器专门放实时日志
    log_container = st.container()
    with log_container:
        st.subheader("📝 实时执行日志")
        
    with st.status("正在运行自动化流程...", expanded=True) as status:
        for task in updated_tasks:
            if task['active']:
                st.write(f"▶️ 正在启动项目: **{task['name']}**")
                env = os.environ.copy()
                env["EMAIL"] = task['email']
                env["PASSWORD"] = task['password']
                env["BYPASS_MODE"] = task['mode']
                # 强制 Python 实时刷新日志流，不缓冲
                env["PYTHONUNBUFFERED"] = "1"
                
                cmd = ["xvfb-run", "--server-args=-screen 0 1920x1080x24", "python", task['script']]
                
                # 使用 pty 或特殊的 bufsize 确保日志一行行跳出来
                process = subprocess.Popen(
                    cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                    text=True, bufsize=1, universal_newlines=True
                )
                
                # 实时刷新日志框
                log_box = st.empty()
                full_log = ""
                
                for line in process.stdout:
                    full_log += line
                    # 限制日志显示长度，防止 UI 崩溃
                    display_log = full_log[-5000:] if len(full_log) > 5000 else full_log
                    log_box.code(display_log)
                
                process.wait()
                if process.returncode == 0:
                    st.success(f"✅ {task['name']} 执行成功")
                else:
                    st.error(f"❌ {task['name']} 执行出错，请检查日志")
        
        status.update(label="✨ 所有任务处理完毕", state="complete", expanded=False)
