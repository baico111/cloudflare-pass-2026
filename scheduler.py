import json
import os
import subprocess
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from huggingface_hub import hf_hub_download, upload_file

# 配置文件根目录 (保持原样)
OUTPUT_DIR = "/app/output"

# ✨ 注入：历史日志目录 (与 app.py 对齐)
HISTORY_DIR = os.path.join(OUTPUT_DIR, "history_logs")
if not os.path.exists(HISTORY_DIR): os.makedirs(HISTORY_DIR, exist_ok=True)

# --- HF 数据集同步逻辑 (保持原样) ---
HF_DATASET_ID = os.environ.get("HF_DATASET_ID") 
HF_TOKEN = os.environ.get("HF_TOKEN")

# ✨ 锁死 CF 配置 (对齐 app.py)
CF_TG_BASE_URL = os.environ.get("TG_PROXY_URL", "https://tgtgcf.yilovesky521.workers.dev")
CF_SECRET_KEY = os.environ.get("TG_AUTH_KEY", "Sky315989021")

def sync_from_cloud():
    """✨ 物理拉取云端最新状态"""
    if HF_TOKEN and HF_DATASET_ID:
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            # ✨ 注入：拉取列表新增 auto_strategy.json
            for f in ["tasks_config.json", "auth_config.json", "auto_strategy.json"]:
                try:
                    hf_hub_download(repo_id=HF_DATASET_ID, filename=f, 
                                    local_dir=OUTPUT_DIR, repo_type="dataset", token=HF_TOKEN)
                except: pass # 容错：如果云端还没这个文件则跳过
            print("[+] 云端时间表及策略同步完成")
        except Exception as e: print(f"[!] 云端拉取失败: {e}")

def sync_to_cloud(local_full_path, repo_path):
    if HF_TOKEN and HF_DATASET_ID:
        try:
            upload_file(path_or_fileobj=local_full_path, path_in_repo=repo_path, 
                        repo_id=HF_DATASET_ID, repo_type="dataset", token=HF_TOKEN)
        except: pass

# ✨ 注入：自动化简报推送函数 (对齐 Web 面板策略)
def auto_send_daily_report():
    """读取 Web 面板配置的策略并决定是否推送简报"""
    strategy_path = os.path.join(OUTPUT_DIR, "auto_strategy.json")
    if not os.path.exists(strategy_path):
        report_hour = 9 # 默认 9 点
        report_enabled = True
    else:
        try:
            with open(strategy_path, 'r') as f:
                strat = json.load(f)
                report_hour = strat.get('report_hour', 9)
                report_enabled = strat.get('report_enabled', True)
        except:
            report_hour, report_enabled = 9, True

    if not report_enabled: return

    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz)
    
    # 检测当前小时是否匹配网页设置的时间 (15分钟容错窗口)
    if now.hour == report_hour and now.minute <= 15:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id: return

        # 聚合当前所有任务状态
        all_tasks_path = os.path.join(OUTPUT_DIR, "tasks_config.json")
        if not os.path.exists(all_tasks_path): return
        with open(all_tasks_path, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
            
        active_tasks = [t for t in tasks if t.get('active')]
        report_text = f"📊 *矩阵内核策略简报 ({now.strftime('%H:%M')})*\n"
        report_text += f"━━━━━━━━━━━━━━━\n"
        report_text += f"✅ 活跃轨道: {len(active_tasks)}\n"
        report_text += f"🤖 自动模式: 已激活\n\n"
        report_text += "📅 队列预告:\n"
        
        sorted_tasks = sorted(active_tasks, key=lambda x: x.get('next_run', '9999'))[:3]
        for t in sorted_tasks:
            report_text += f"🔹 {t['name']}: {t.get('next_run', 'N/A')}\n"

        try:
            requests.post(f"{CF_TG_BASE_URL.rstrip('/')}/{token}/sendMessage", 
                         json={"chat_id": chat_id, "text": report_text, "parse_mode": "Markdown"},
                         headers={"X-Custom-Auth": CF_SECRET_KEY}, timeout=10)
            print("[+] 策略简报推送成功")
        except: pass

def run_scheduler():
    # ✨ 核心接电：先同步
    sync_from_cloud()

    # ✨ 注入：执行策略检查
    auto_send_daily_report()

    status_files = list(Path(OUTPUT_DIR).rglob("*.status.json"))
    
    if not status_files:
        print("[*] 尚未发现任何账号配置文件，调度器待命。")
        return

    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz)

    for config_path in status_files:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                task = json.load(f)
        except Exception as e:
            print(f"[!] 读取 {config_path.name} 失败: {e}")
            continue

        if not task.get('active', True): 
            continue
        
        last_run_str = task.get('last_run')
        freq = task.get('freq', 3)
        
        should_run = False
        if not last_run_str or last_run_str == "从未运行":
            should_run = True
        else:
            try:
                last_run_time = datetime.strptime(str(last_run_str), "%Y-%m-%d %H:%M:%S").replace(tzinfo=bj_tz)
                if now >= (last_run_time + timedelta(days=freq)):
                    should_run = True
            except (ValueError, TypeError):
                should_run = True

        if should_run:
            # ✨ 物理注入：检测空值拦截逻辑
            if not task.get('email') or not task.get('password'):
                print(f"[!] 跳过任务 {task.get('name')}: 账号或密码为空")
                continue

            for old in ["final_result.png", "error.png"]:
                if os.path.exists(old): os.remove(old)

            selected_mode = task.get('mode', '单浏览器模式 (对应脚本: simple_bypass.py)')
            script_name = task.get('script', 'katabump_renew.py')
            print(f"[*] [后台保活启动] 账号: {task.get('email')} | 脚本: {script_name}")
            
            env = os.environ.copy()
            env.update({
                "EMAIL": str(task['email']), 
                "PASSWORD": str(task['password']), 
                "BYPASS_MODE": str(selected_mode), 
                "PYTHONUNBUFFERED": "1",
                "SERVER_ID": str(task.get('server_id', '177688')),
                "PROXY": str(task.get('proxy', '')),
                "RENEW_ID": str(task.get('renew_id', '')),
                "TG_PROXY_URL": str(CF_TG_BASE_URL),
                "TG_AUTH_KEY": str(CF_SECRET_KEY),
                "TELEGRAM_BOT_TOKEN": str(os.environ.get("TELEGRAM_BOT_TOKEN", "")),
                "TELEGRAM_CHAT_ID": str(os.environ.get("TELEGRAM_CHAT_ID", ""))
            })

            if script_name == "pella_renew.py":
                env["PELLA_EMAIL"] = str(task['email'])
                env["GMAIL_APP_PASSWORD"] = str(task['password'])
            
            if script_name == "luneshost.py":
                env["STAY_TIME"] = str(task.get('stay_time', 10))
                env["REFRESH_COUNT"] = str(task.get('refresh_count', 3))
                env["REFRESH_INTERVAL"] = str(task.get('refresh_interval', 5))
            
            try:
                process = subprocess.Popen([
                    "xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24", 
                    "python", script_name
                ], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                
                full_log = []
                for line in process.stdout:
                    print(line.strip()) 
                    full_log.append(line.strip())
                process.wait()

                log_file = os.path.join(HISTORY_DIR, f"{task['name']}.log")
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n[{datetime.now(bj_tz).strftime('%Y-%m-%d %H:%M:%S')}] BACKGROUND_RUN_STATUS: {process.returncode}\n")
                    f.write("\n".join(full_log[-15:]) + "\n" + "="*30)

                if process.returncode != 0: raise Exception(f"进程异常退出 Code: {process.returncode}")
                
                proj_name, email = script_name.replace('.py', ''), task['email']
                if os.path.exists("final_result.png"):
                    sync_to_cloud("final_result.png", f"{proj_name}/{email}.png")
                
                # 1. 更新当前任务的时间
                task['last_run'] = now.strftime("%Y-%m-%d %H:%M:%S")
                try:
                    next_dt = now + timedelta(days=task['freq'])
                    task['next_run'] = next_dt.strftime('%Y-%m-%d %H:%M:%S')
                except: pass

                # 2. 写入单独的 .status.json 文件
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)
                
                # 3. ✨ 物理注入：同步更新汇总文件 tasks_config.json
                all_config_path = os.path.join(OUTPUT_DIR, "tasks_config.json")
                if os.path.exists(all_config_path):
                    with open(all_config_path, 'r', encoding='utf-8') as f_all:
                        all_tasks = json.load(f_all)
                    
                    # 在汇总列表中寻找并匹配该任务（根据 email 和 script 匹配）
                    updated = False
                    for t in all_tasks:
                        if t.get('email') == task.get('email') and t.get('script') == task.get('script'):
                            t['last_run'] = task['last_run']
                            t['next_run'] = task['next_run']
                            updated = True
                            break
                    
                    if updated:
                        with open(all_config_path, 'w', encoding='utf-8') as f_save:
                            json.dump(all_tasks, f_save, ensure_ascii=False, indent=2)
                        # ✨ 物理回传：同步汇总文件到云端
                        sync_to_cloud(all_config_path, "tasks_config.json")
                
                # 同步单独状态文件到云端
                repo_path = str(config_path.relative_to(OUTPUT_DIR))
                sync_to_cloud(str(config_path), repo_path)
                print(f"[+] {email} 后台续期成功，汇总文件已同步。")

            except Exception as e:
                proj_name, email = script_name.replace('.py', ''), task['email']
                if os.path.exists("error.png"):
                    sync_to_cloud("error.png", f"{proj_name}/{email}_error.png")
                print(f"[!] {email} 后台执行失败: {e}")

if __name__ == "__main__":
    run_scheduler()
