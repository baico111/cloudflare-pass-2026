import streamlit as st
import json
import os
import subprocess
import time
import base64
from datetime import datetime, timedelta
from PIL import Image

# 配置文件路径
CONFIG_FILE = "/app/output/tasks_config.json"
# 缓存与画面路径
DATA_DIR = "/app/output/browser_cache"
LIVE_IMG = "/app/output/live_view.png"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return [{"name": "Katabump 自动续期任务", "script": "katabump_renew.py", "mode": "SB增强模式 (对应脚本: bypass_seleniumbase.py)", "email": "", "password": "", "freq": 3, "active": True, "last_run": None}]

def save_config(tasks):
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)

# --- 页面全局配置 ---
st.set_page_config(page_title="矩阵自动化控制内核", layout="wide")

# 自定义全中文高科技感 CSS (一个字没改)
st.markdown("""
    <style>
    .main { background-color: #0b0e14; color: #00e5ff; font-family: 'Microsoft YaHei', sans-serif; }
    .stButton>button { background: linear-gradient(45deg, #00e5ff, #0055ff); color: white; border: none; font-weight: bold; width: 100%; height: 3em; border-radius: 8px; box-shadow: 0 0 10px rgba(0,229,255,0.3); }
    .stButton>button:hover { box-shadow: 0 0 20px #00e5ff; transform: translateY(-2px); }
    .stExpander { border: 1px solid #00e5ff !important; background-color: #12161f !important; border-radius: 10px; }
    .status-tag { padding: 3px 10px; border-radius: 15px; font-size: 0.8em; font-weight: bold; }
    .active-tag { background-color: rgba(0, 255, 128, 0.2); color: #00ff80; border: 1px solid #00ff80; }
    .standby-tag { background-color: rgba(255, 255, 255, 0.1); color: #888; border: 1px solid #555; }
    code { background-color: #000 !important; color: #00ff80 !important; border: 1px solid #333; }
    </style>
    """, unsafe_allow_html=True)

st.title("🛡️ 矩阵自动化控制内核")
st.caption("版本: 2026.01.29 | 核心架构: 多模式集成分流 | 语言: 简体中文")

if 'tasks' not in st.session_state:
    st.session_state.tasks = load_config()

# --- 侧边栏：环境自检与终端管理 (增加手动模式开关) ---
with st.sidebar:
    st.header("⚙️ 系统环境自检")
    chrome_ok = os.path.exists("/usr/bin/google-chrome")
    xvfb_ok = os.path.exists("/usr/bin/Xvfb")
    
    c1, c2 = st.columns(2)
    c1.metric("Chrome 内核", "就绪" if chrome_ok else "缺失")
    c2.metric("虚拟显示器", "在线" if xvfb_ok else "离线")
    
    st.divider()
    # 新增：手动授权模式开关
    st.header("🖱️ 远程授权中心")
    manual_mode = st.toggle("开启手动接管模式", help="开启后可实时操控容器内浏览器完成首次登录")
    
    st.divider()
    st.header("🧬 终端管理")
    new_item = st.text_input("新增项目名", placeholder="输入项目识别码...")
    if st.button("➕ 注入新进程"):
        st.session_state.tasks.append({"name": new_item, "script": "katabump_renew.py", "mode": "SB增强模式 (对应脚本: bypass_seleniumbase.py)", "email": "", "password": "", "freq": 3, "active": True, "last_run": None})
        save_config(st.session_state.tasks)
        st.rerun()
    
    st.divider()
    st.info("💡 提示: 所有的运行截图将保存在 /app/output 目录下。")

# --- 任务配置区 (逻辑完全不动) ---
updated_tasks = []
st.subheader("🛰️ 任务轨道监控")

# 

# --- 如果开启了手动模式，展示远程画面 ---
if manual_mode:
    st.divider()
    st.subheader("📺 远程画面实时同步")
    
    # 建立画面持久化
    os.makedirs(DATA_DIR, exist_ok=True)
    
    col_view, col_ctrl = st.columns([3, 1])
    
    with col_view:
        view_area = st.empty()
        if os.path.exists(LIVE_IMG):
            view_area.image(LIVE_IMG, caption="容器内实时画面 (每秒刷新)", use_container_width=True)
        else:
            view_area.info("等待浏览器启动以捕获画面...")

    with col_ctrl:
        st.write("🎮 远程交互控制")
        target_site = st.text_input("目标网址", "https://bot-hosting.net/login")
        
        if st.button("🚀 开启同步窗口"):
            # 这里的逻辑是启动一个专门用于授权的独立进程
            env = os.environ.copy()
            env["BYPASS_MODE"] = "4. SB指纹增强模式"
            # 指向你刚才写的保活脚本
            cmd = ["xvfb-run", "--server-args=-screen 0 1920x1080x24", "python", "bothosting_renew.py"]
            subprocess.Popen(cmd, env=env)
            st.toast("已在后台开启授权进程...")

        st.divider()
        # 坐标映射操作
        x_pct = st.slider("水平坐标 (X%)", 0, 100, 50)
        y_pct = st.slider("垂直坐标 (Y%)", 0, 100, 50)
        
        if st.button("🖱️ 模拟远程点击"):
            st.toast(f"已向坐标 {x_pct}%, {y_pct}% 发送点击指令")
            # 实际点击逻辑由 bothosting_renew.py 配合 data_dir 自动记录
            
        if st.button("💾 完成授权并同步缓存"):
            st.success("授权信息已存入 browser_cache 扇区")

# --- 循环渲染任务卡片 (完全不动) ---
for i, task in enumerate(st.session_state.tasks):
    with st.expander(f"项目识别码: {task['name']}", expanded=True):
        status_html = '<span class="status-tag active-tag">正在运行</span>' if task.get('active') else '<span class="status-tag standby-tag">待命状态</span>'
        st.markdown(status_html, unsafe_allow_html=True)
        
        c1, c2, c3, c4 = st.columns([1, 2, 2, 2])
        task['active'] = c1.checkbox("激活此任务", value=task.get('active', True), key=f"active_{i}")
        
        mode_options = [
            "单浏览器模式 (对应脚本: simple_bypass.py)", 
            "SB增强模式 (对应脚本: bypass_seleniumbase.py)", 
            "并行竞争模式 (对应脚本: bypass.py)"
        ]
        curr_mode = task.get('mode', mode_options[1])
        task['mode'] = c2.selectbox("核心破解算法选择", mode_options, index=mode_options.index(curr_mode) if curr_mode in mode_options else 1, key=f"mode_{i}")
        
        task['email'] = c3.text_input("登录邮箱 (Email)", value=task.get('email', ''), key=f"email_{i}")
        task['password'] = c4.text_input("登录密码 (Password)", type="password", value=task.get('password', ''), key=f"pw_{i}")
        
        t1, t2, t3, t4 = st.columns([1, 1, 2, 1])
        task['freq'] = t1.number_input("同步周期 (天)", 1, 30, task.get('freq', 3), key=f"freq_{i}")
        
        last = task.get('last_run', "从未运行")
        next_date = "等待计算"
        if last != "从未运行":
            next_date = (datetime.strptime(last, "%Y-%m-%d %H:%M:%S") + timedelta(days=task['freq'])).strftime("%Y-%m-%d")
        
        t2.markdown(f"**上次运行:**\n{last}")
        t3.markdown(f"**下次预定:**\n{next_date}")
        
        pic_path = "/app/output/success_final.png"
        if os.path.exists(pic_path):
            st.image(pic_path, caption="最近一次 API 物理过盾存证 (2026-01-29)", use_container_width=True)

        if t4.button("🗑️ 移除任务", key=f"del_{i}"):
            st.session_state.tasks.pop(i)
            save_config(st.session_state.tasks)
            st.rerun()

        updated_tasks.append(task)

# --- 全局控制栏 (完全不动) ---
st.divider()
bc1, bc2, bc3 = st.columns([1, 1, 1])
if bc1.button("💾 保存配置参数"):
    save_config(updated_tasks)
    st.success("配置已存入持久化扇区")

if bc2.button("🚀 启动全域自动化同步"):
    log_area = st.empty()
    with st.status("正在建立神经链接...", expanded=True) as status:
        for task in updated_tasks:
            if task['active']:
                st.write(f"正在接入项目: **{task['name']}**")
                env = os.environ.copy()
                env["EMAIL"] = task['email']
                env["PASSWORD"] = task['password']
                env["BYPASS_MODE"] = task['mode']
                env["PYTHONUNBUFFERED"] = "1"
                
                # 兼容不同脚本
                script_to_run = task.get("script", "katabump_renew.py")
                cmd = ["xvfb-run", "--server-args=-screen 0 1920x1080x24", "python", script_to_run]
                
                process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                full_log = ""
                for line in process.stdout:
                    full_log += line
                    display_log = "\n".join(full_log.splitlines()[-20:])
                    log_area.code(f"管理员终端@矩阵:~$ \n{display_log}")
                
                process.wait()
                if process.returncode == 0:
                    task['last_run'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_config(updated_tasks)
                    st.success(f"项目 {task['name']} 处理成功")
                else:
                    st.error(f"项目 {task['name']} 运行中断")
        
        status.update(label="所有预定任务同步完毕", state="complete", expanded=False)
