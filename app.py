import streamlit as st
import json
import os
import subprocess
import time
import requests
from datetime import datetime, timedelta, timezone
from huggingface_hub import hf_hub_download, upload_file, delete_file
from collections import deque
# ✨ 注入：引入自动刷新组件
from streamlit_autorefresh import st_autorefresh

# 配置文件路径锁定
OUTPUT_DIR = "/app/output"
if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

CONFIG_FILE = os.path.join(OUTPUT_DIR, "tasks_config.json")
AUTH_FILE = os.path.join(OUTPUT_DIR, "auth_config.json")
# ✨ 注入：自动化策略配置文件
AUTO_STRATEGY_FILE = os.path.join(OUTPUT_DIR, "auto_strategy.json")
HISTORY_DIR = os.path.join(OUTPUT_DIR, "history_logs")
if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR, exist_ok=True)

# ✨ 锁死从系统环境变量获取的 CF 配置
CF_TG_BASE_URL = os.environ.get("TG_PROXY_URL", "https://tgtgcf.yilovesky521.workers.dev")
CF_SECRET_KEY = os.environ.get("TG_AUTH_KEY", "Sky315989021")

HF_DATASET_ID = os.environ.get("HF_DATASET_ID") 
HF_TOKEN = os.environ.get("HF_TOKEN")

if 'cloud_sync_status' not in st.session_state:
    st.session_state.cloud_sync_status = "未就绪"

# ✨ 注入：策略加载函数
def load_strategy():
    if os.path.exists(AUTO_STRATEGY_FILE):
        try:
            with open(AUTO_STRATEGY_FILE, 'r') as f:
                return json.load(f)
        except: pass
    return {"report_hour": 9, "report_enabled": True}

# ✨ 注入：策略保存函数
def save_strategy(strategy):
    with open(AUTO_STRATEGY_FILE, 'w') as f:
        json.dump(strategy, f)
    sync_to_cloud("auto_strategy.json")

def send_daily_report(tasks):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return
    
    active_tasks = [t for t in tasks if t.get('active')]
    success_count = len([t for t in active_tasks if "从未运行" not in t.get('last_run', '')])
    
    report_text = f"📊 *矩阵内核手动简报*\n"
    report_text += f"━━━━━━━━━━━━━━━\n"
    report_text += f"✅ 运行中任务: {len(active_tasks)}\n"
    report_text += f"📈 已激活节点: {success_count}\n"
    report_text += f"📅 报告时间: {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    report_text += "近期预定:\n"
    
    sorted_tasks = sorted(active_tasks, key=lambda x: x.get('next_run', '9999'))[:3]
    for t in sorted_tasks:
        report_text += f"🔹 {t['name']}: {t.get('next_run', 'N/A')}\n"
        
    try:
        requests.post(f"{CF_TG_BASE_URL.rstrip('/')}/{token}/sendMessage", 
                     json={"chat_id": chat_id, "text": report_text, "parse_mode": "Markdown"},
                     headers={"X-Custom-Auth": CF_SECRET_KEY}, timeout=10)
    except: pass

def sync_from_cloud():
    if HF_TOKEN and HF_DATASET_ID:
        for f_name in ["tasks_config.json", "auth_config.json", "auto_strategy.json", "error.png", "final_result.png"]:
            try:
                hf_hub_download(repo_id=HF_DATASET_ID, filename=f_name, 
                                local_dir=OUTPUT_DIR, repo_type="dataset", token=HF_TOKEN)
                st.session_state.cloud_sync_status = "同步成功"
            except: 
                st.session_state.cloud_sync_status = "同步异常"

def sync_to_cloud(filename):
    if HF_TOKEN and HF_DATASET_ID:
        full_path = os.path.join(OUTPUT_DIR, filename)
        if os.path.exists(full_path):
            try:
                upload_file(path_or_fileobj=full_path, path_in_repo=filename,
                            repo_id=HF_DATASET_ID, repo_type="dataset", token=HF_TOKEN)
                st.session_state.cloud_sync_status = "已上传"
            except: 
                st.session_state.cloud_sync_status = "上传失败"

def delete_from_cloud(repo_path):
    if HF_TOKEN and HF_DATASET_ID:
        try:
            delete_file(path_in_repo=repo_path, repo_id=HF_DATASET_ID, 
                        repo_type="dataset", token=HF_TOKEN)
        except: pass

if 'initialized' not in st.session_state:
    sync_from_cloud()
    st.session_state.initialized = True

def load_auth():
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r') as f:
                return json.load(f).get("access_code", "admin123")
        except: pass
    return os.environ.get("WEB_ACCESS_CODE", "admin123")

def save_auth(new_code):
    os.makedirs(os.path.dirname(AUTH_FILE), exist_ok=True)
    with open(AUTH_FILE, 'w') as f:
        json.dump({"access_code": new_code}, f)
    sync_to_cloud("auth_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: pass
    # ✨ 物理修改：取消默认注入 Lunes 任务模板，返回空列表
    return []

def save_config(tasks):
    bj_tz = timezone(timedelta(hours=8))
    for task in tasks:
        last = task.get('last_run', "从未运行")
        if last != "从未运行":
            try:
                next_dt = (datetime.strptime(last, '%Y-%m-%d %H:%M:%S') + timedelta(days=task['freq']))
                task['next_run'] = next_dt.strftime('%Y-%m-%d %H:%M:%S')
            except: task['next_run'] = "计算异常"
        else: task['next_run'] = "等待首次运行"

        proj_name = task.get('script').replace('.py', '')
        email = task.get('email', 'default')
        proj_dir = os.path.join(OUTPUT_DIR, proj_name)
        if not os.path.exists(proj_dir): os.makedirs(proj_dir, exist_ok=True)
        file_path = os.path.join(proj_dir, f"{email}.status.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(task, f, ensure_ascii=False, indent=2)
        sync_to_cloud(f"{proj_name}/{email}.status.json")

    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    temp_file = CONFIG_FILE + ".tmp"
    with open(temp_file, 'w', encoding='utf-8') as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    os.replace(temp_file, CONFIG_FILE)
    sync_to_cloud("tasks_config.json")

st.set_page_config(page_title="矩阵自动化控制内核", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .main { background-color: #05070a; color: #a0aec0; font-size: 0.85rem; }
    h1 { font-size: 1.5rem !important; color: #00e5ff !important; text-shadow: 0 0 10px rgba(0,229,255,0.5); }
    .stExpander { border: 1px solid rgba(0, 229, 255, 0.2) !important; background-color: rgba(18, 22, 31, 0.8) !important; border-radius: 8px !important; margin-bottom: 8px !important; }
    .stButton>button { background: linear-gradient(45deg, #0099ff, #0055ff); color: white; border: none; font-size: 0.75rem !important; border-radius: 4px; padding: 0.2rem 0.5rem; height: auto !important; }
    .stButton>button:hover { box-shadow: 0 0 15px #00e5ff; transform: translateY(-1px); }
    .status-tag { padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: bold; }
    .active-tag { background-color: rgba(0, 255, 128, 0.1); color: #00ff80; border: 1px solid #00ff80; }
    .stTextInput>div>div>input { background-color: #000 !important; color: #00ff80 !important; font-size: 0.8rem !important; }
    .highlight-time { color: #00e5ff !important; font-weight: 900 !important; background: rgba(0, 229, 255, 0.1); padding: 2px 5px; border-radius: 3px; }
    code { font-size: 0.7rem !important; line-height: 1.2 !important; }
    .queue-card { background: rgba(255,255,255,0.03); border-left: 3px solid #00e5ff; padding: 8px; margin: 4px 0; border-radius: 0 4px 4px 0; }
    </style>
    """, unsafe_allow_html=True)

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# ✨ 物理修复：提前初始化 is_running 状态
if 'is_running' not in st.session_state:
    st.session_state.is_running = False

current_access_code = load_auth()

if not st.session_state.authenticated:
    st.title("🛡️ 内核访问授权")
    col_l, col_m, col_r = st.columns([1, 2, 1])
    with col_m:
        auth_code = st.text_input("请输入矩阵授权码", type="password")
        if st.button("验证身份"):
            if auth_code == current_access_code:
                st.session_state.authenticated = True
                st.rerun()
            else: st.error("授权码错误。")
    st.stop()

# ✨ 物理注入：设置每 30 秒自动刷新一次 UI
if not st.session_state.is_running:
    st_autorefresh(interval=30000, key="data_refresh")

st.title("🛡️ 矩阵自动化控制内核")

if 'tasks' not in st.session_state:
    st.session_state.tasks = load_config()

# ✨ 注入：由于自动刷新会重置逻辑，这里强制每一轮都重新加载最新磁盘配置
if not st.session_state.is_running:
    st.session_state.tasks = load_config()

with st.sidebar:
    st.header("⚙️ 终端管理")
    
    c_sync = st.session_state.cloud_sync_status
    c_color = "#00ff80" if "成功" in c_sync or "上传" in c_sync else "#ff4b4b"
    st.markdown(f"☁️ 云端同步: <span style='color:{c_color}; font-weight:bold;'>{c_sync}</span>", unsafe_allow_html=True)
    
    # ✨ 注入：自动化策略中心
    with st.expander("🤖 自动化策略中心", expanded=False):
        strategy = load_strategy()
        st.markdown("---")
        strategy['report_enabled'] = st.toggle("开启每日自动简报", value=strategy.get('report_enabled', True))
        strategy['report_hour'] = st.number_input("推送时间 (北京24h)", 0, 23, value=strategy.get('report_hour', 9))
        if st.button("💾 应用自动化策略"):
            save_strategy(strategy)
            st.success("策略已同步至云端")

    if st.button("📢 发送即时简报"):
        send_daily_report(st.session_state.tasks)
        st.toast("简报已推送到 Telegram")

    if st.session_state.is_running:
        st.warning("⚡ 引擎进程占用中...")
    else:
        st.success("💎 调度引擎就绪")
        
    new_item = st.text_input("项目识别码", placeholder="识别码...")
    script_options = ["katabump_renew.py", "luneshost.py", "pella_renew.py"]
    selected_script = st.selectbox("核心脚本", script_options)
    if st.button("➕ 注入新进程"):
        new_task = {"name": new_item, "script": selected_script, "mode": "SB增强模式 (对应脚本: bypass_seleniumbase.py)", "email": "", "password": "", "freq": 3, "active": True, "last_run": "从未运行", "stay_time": 10, "refresh_count": 3, "refresh_interval": 5, "server_id": "52794", "proxy": "", "renew_id": ""}
        if selected_script == "luneshost.py": new_task.update({"stay_time": 10, "refresh_count": 3, "refresh_interval": 5, "server_id": "52794"})
        if selected_script == "pella_renew.py": new_task.update({"server_id": "2b3bbeef0eeb452299a11e431c3c2d5b", "renew_id": "m4w0wJrEmgEC"})
        st.session_state.tasks.append(new_task)
        save_config(st.session_state.tasks)
        st.rerun()

    # ✨ 注入：SOCKS5 链路测速仪 (位置迁移后的预执行队列上方)
    st.divider()
    with st.expander("🔌 SOCKS5 链路测速仪", expanded=False):
        test_proxy = st.text_input("代理地址", placeholder="user:pass@host:port", key="proxy_tester_input")
        if st.button("🚀 拨号测试"):
            if test_proxy:
                # 协议自动清洗补全
                final_proxy = test_proxy if test_proxy.startswith(("http", "socks")) else f"socks5://{test_proxy}"
                try:
                    st.info("📡 正在尝试建立中继链路...")
                    proxies = {"http": final_proxy, "https": final_proxy}
                    start_t = time.time()
                    resp = requests.get("https://www.google.com", proxies=proxies, timeout=15)
                    latency = round((time.time() - start_t) * 1000)
                    if resp.status_code == 200:
                        st.success(f"✅ 链路通畅! 延迟: {latency}ms")
                    else:
                        st.warning(f"⚠️ 握手成功但返回异常: {resp.status_code}")
                except Exception as e:
                    st.error(f"❌ 链路中断: 无法连接至代理或超时")
            else:
                st.warning("请输入地址后再测试")

    st.markdown("### 📅 预执行队列流")
    sorted_tasks = sorted([t for t in st.session_state.tasks if t.get('active')], 
                         key=lambda x: x.get('next_run', '9999'))[:4]
    for stask in sorted_tasks:
        st.markdown(f"""<div class='queue-card'><b>{stask['name']}</b><br><small>Next: {stask.get('next_run')}</small></div>""", unsafe_allow_html=True)
    
    st.markdown("### 📊 资源负载")
    usage_color = "#00ff80" if not st.session_state.is_running else "#ff4b4b"
    st.markdown(f"<h3 style='color:{usage_color}; text-align:center;'>{'IDLE' if not st.session_state.is_running else 'BUSY'}</h3>", unsafe_allow_html=True)
    st.progress(100 if st.session_state.is_running else 0)
    
    st.divider()
    with st.expander("🔐 安全设置"):
        old_code = st.text_input("当前授权码", type="password", key="old_code")
        new_code = st.text_input("新授权码", type="password", key="new_code")
        if st.button("确认修改密码"):
            if old_code == current_access_code:
                if new_code:
                    save_auth(new_code)
                    st.success("授权码已更新。")
                    time.sleep(1)
                    st.rerun()
                else: st.warning("新授权码不能为空")
            else: st.error("当前授权码验证失败")

    st.header("📡 链路诊断")
    if st.button("🚀 测试 TG 通知"):
        try:
            from seleniumbase import SB 
            token = os.environ.get("TELEGRAM_BOT_TOKEN")
            chat_id = os.environ.get("TELEGRAM_CHAT_ID")
            test_shot = os.path.join(OUTPUT_DIR, "baidu_test.png")
            
            with SB(uc=True, xvfb=True) as sb:
                st.info("🌐 正在抓取 Baidu 实时快照...")
                sb.open("https://www.baidu.com") 
                sb.save_screenshot(test_shot)
            
            target_url = f"{CF_TG_BASE_URL.rstrip('/')}/{token}/sendPhoto"
            headers = {"X-Custom-Auth": CF_SECRET_KEY}
            
            with open(test_shot, 'rb') as f:
                r = requests.post(target_url, 
                                  data={"chat_id": chat_id, "caption": "🔔 链路回滚测试：Baidu 截图同步成功"}, 
                                  files={'photo': f}, 
                                  headers=headers, 
                                  timeout=30)
            
            if r.status_code == 200: 
                st.success("✅ 通信 & 截图发送成功")
                sync_to_cloud("baidu_test.png")
            else: 
                st.error(f"❌ 报错: {r.status_code}")
                requests.post(f"{CF_TG_BASE_URL.rstrip('/')}/{token}/sendMessage", 
                             json={"chat_id": chat_id, "text": f"⚠️ 截图失败({r.status_code})，文字链路存活"}, 
                             headers=headers)
        except Exception as e: st.error(f"🔥 诊断崩溃: {str(e)}")

    st.divider()
    if st.button("🚪 退出授权"):
        st.session_state.authenticated = False
        st.rerun()

updated_tasks = st.session_state.tasks
bj_tz = timezone(timedelta(hours=8))

for i, task in enumerate(updated_tasks):
    with st.expander(f"🛰️ {task['name']} | {task.get('script')}", expanded=True):
        head_1, head_2 = st.columns([1, 5])
        status_html = '<span class="status-tag active-tag">在线</span>' if task.get('active') else '<span class="status-tag">离线</span>'
        head_1.markdown(status_html, unsafe_allow_html=True)
        task['active'] = head_2.checkbox("激活该轨道进程", value=task.get('active', True), key=f"active_{i}")

        if task.get('script') == "pella_renew.py":
            c1, c2, c3, c4, c5, c6 = st.columns([1.2, 1.8, 2.5, 0.8, 1.2, 1.8])
            c1.text_input("算法模式", value="基站穿透", disabled=True, key=f"algo_dis_{i}")
            task['email'] = c2.text_input("Email", value=task.get('email', ''), key=f"email_{i}")
            task['password'] = c3.text_input("Kuma Status URL", value=task.get('password', ''), key=f"pw_{i}", help="填写你的 Kuma 状态页地址")
            task['server_id'] = c4.text_input("ID", value=task.get('server_id', ''), key=f"sid_{i}")
            task['renew_id'] = c5.text_input("续期ID", value=task.get('renew_id', 'm4w0wJrEmgEC'), key=f"rid_{i}")
            task['proxy'] = c6.text_input("SOCKS5 代理", value=task.get('proxy', ''), key=f"proxy_{i}")
        else:
            c1, c2, c3, c4, c5 = st.columns([1.5, 1.8, 1.8, 0.8, 2])
            task['mode'] = c1.selectbox("破解算法", ["单浏览器模式 (对应脚本: simple_bypass.py)", "SB增强模式 (对应脚本: bypass_seleniumbase.py)", "并行竞争模式 (对应脚本: bypass.py)"], key=f"mode_{i}")
            task['email'] = c2.text_input("Email", value=task.get('email', ''), key=f"email_{i}")
            task['password'] = c3.text_input("Password", type="password", value=task.get('password', ''), key=f"pw_{i}")
            task['server_id'] = c4.text_input("ID", value=task.get('server_id', ''), key=f"sid_{i}")
            task['proxy'] = c5.text_input("SOCKS5 代理", value=task.get('proxy', ''), key=f"proxy_{i}")

        st.markdown("<div style='margin: 5px 0; border-top: 1px solid rgba(255,255,255,0.05);'></div>", unsafe_allow_html=True)
        if task.get('script') == "luneshost.py":
            lx_freq, lx1, lx2, lx3 = st.columns([1, 1, 1, 1])
            task['freq'] = lx_freq.number_input("周期(天)", 1, 30, task.get('freq', 3), key=f"freq_{i}")
            task['stay_time'] = lx1.number_input("停留(s)", 5, 300, task.get('stay_time', 10), key=f"stay_{i}")
            task['refresh_count'] = lx2.number_input("刷新(次)", 1, 20, task.get('refresh_count', 3), key=f"count_{i}")
            task['refresh_interval'] = lx3.number_input("间隔(s)", 1, 60, task.get('refresh_interval', 5), key=f"interval_{i}")
        else:
            t_freq, t_empty1, t_empty2 = st.columns([1, 1, 1])
            task['freq'] = t_freq.number_input("周期(天)", 1, 30, task.get('freq', 3), key=f"freq_{i}")

        st.markdown("<div style='margin: 5px 0; border-top: 1px solid rgba(255,255,255,0.05);'></div>", unsafe_allow_html=True)
        t_time1, t_time2 = st.columns(2)
        last = task.get('last_run', "从未运行")
        next_date = task.get('next_run', "等待运行")
        t_time1.markdown(f"上次运行: <span class='highlight-time'>{last}</span>", unsafe_allow_html=True)
        t_time2.markdown(f"下次预定: <span class='highlight-time'>{next_date}</span>", unsafe_allow_html=True)

        with st.expander("📝 查看历史链路记录"):
            log_path = os.path.join(HISTORY_DIR, f"{task['name']}.log")
            if os.path.exists(log_path):
                with open(log_path, 'r', encoding='utf-8') as f:
                    st.text_area("历史存证", f.read(), height=100, key=f"hist_log_{i}")
            else: st.caption("暂无历史存证数据")

        st.markdown("<div style='margin: 8px 0;'></div>", unsafe_allow_html=True)
        btn_1, btn_2, btn_3, _ = st.columns([1, 1, 1, 1.5])
        if btn_1.button("💾 保存", key=f"save_{i}"):
            save_config(updated_tasks)
            st.toast(f"{task['name']} 已保存")
            
        run_btn_label = "🚀 同步" if not st.session_state.is_running else "⏳ 排队中"
        if btn_2.button(run_btn_label, key=f"run_{i}", disabled=st.session_state.is_running):
            st.session_state.is_running = True
            log_area = st.empty()
            with st.status(f"正在建立虚拟总线连接...", expanded=True) as status:
                env = os.environ.copy()
                env.update({
                    "EMAIL": str(task['email']), "PASSWORD": str(task['password']), 
                    "BYPASS_MODE": str(task['mode']), "PYTHONUNBUFFERED": "1",
                    "TG_PROXY_URL": str(CF_TG_BASE_URL), "TG_AUTH_KEY": str(CF_SECRET_KEY),
                    "SERVER_ID": str(task.get('server_id', '')), "PROXY": str(task.get('proxy', '')), 
                    "RENEW_ID": str(task.get('renew_id', '')),
                    "TELEGRAM_BOT_TOKEN": str(os.environ.get("TELEGRAM_BOT_TOKEN", "")),
                    "TELEGRAM_CHAT_ID": str(os.environ.get("TELEGRAM_CHAT_ID", ""))
                })
                if task.get('script') == "pella_renew.py":
                    env.update({"PELLA_EMAIL": str(task['email']), "GMAIL_APP_PASSWORD": str(task['password'])})
                if task.get('script') == "luneshost.py":
                    env.update({"STAY_TIME": str(task.get('stay_time', 10)), "REFRESH_COUNT": str(task.get('refresh_count', 3)), "REFRESH_INTERVAL": str(task.get('refresh_interval', 5))})
                
                process = subprocess.Popen(["xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24", "python", task.get('script')], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                
                log_queue = deque(maxlen=25) 
                full_session_log = []
                for line in process.stdout:
                    log_queue.append(line.strip())
                    full_session_log.append(line.strip())
                    log_area.code("\n".join(log_queue))
                process.wait()

                with open(os.path.join(HISTORY_DIR, f"{task['name']}.log"), 'a', encoding='utf-8') as f:
                    f.write(f"\n[{datetime.now(bj_tz).strftime('%Y-%m-%d %H:%M:%S')}] RUN: {process.returncode}\n")
                    f.write("\n".join(full_session_log[-10:]) + "\n" + "-"*30)

                time.sleep(7) 
                sync_to_cloud("error.png")
                sync_to_cloud("final_result.png")
                
                should_update_ui = True
                if task.get('script') == "pella_renew.py" and "PELLA_SUCCESS_FLAG" not in "\n".join(log_queue):
                    should_update_ui = False
                
                if process.returncode == 0 and should_update_ui:
                    task['last_run'] = datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M:%S")
                    save_config(updated_tasks)
                    status.update(label="进程同步成功", state="complete")
                    st.session_state.is_running = False
                    st.rerun()
                else:
                    status.update(label="链路任务异常", state="error")
                    st.error("❗ 运行失败。")
                    st.session_state.is_running = False

        if btn_3.button("🗑️ 移除", key=f"del_{i}"):
            target_task = st.session_state.tasks[i]
            proj_name = target_task.get('script').replace('.py', '')
            email_tag = target_task.get('email', 'default')
            
            # ✨ 物理注入：在移除任务时，同步删除本地磁盘上的 status 文件，彻底根除后台重启执行
            local_status_path = os.path.join(OUTPUT_DIR, proj_name, f"{email_tag}.status.json")
            if os.path.exists(local_status_path):
                os.remove(local_status_path)
                
            cloud_path = f"{proj_name}/{email_tag}.status.json"
            st.session_state.tasks.pop(i)
            save_config(st.session_state.tasks)
            delete_from_cloud(cloud_path)
            st.rerun()

st.divider()
st.caption("矩阵内核 independent Autonomous Drive · 信息已加密")
