import json
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from huggingface_hub import hf_hub_download, upload_file

# 配置文件根目录 (保持原样)
OUTPUT_DIR = "/app/output"

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
            for f in ["tasks_config.json", "auth_config.json"]:
                hf_hub_download(repo_id=HF_DATASET_ID, filename=f, 
                                local_dir=OUTPUT_DIR, repo_type="dataset", token=HF_TOKEN)
            print("[+] 云端时间表同步完成")
        except Exception as e: print(f"[!] 云端拉取失败: {e}")

def sync_to_cloud(local_full_path, repo_path):
    if HF_TOKEN and HF_DATASET_ID:
        try:
            upload_file(path_or_fileobj=local_full_path, path_in_repo=repo_path, 
                        repo_id=HF_DATASET_ID, repo_type="dataset", token=HF_TOKEN)
        except: pass

def run_scheduler():
    # ✨ 核心接电：先同步
    sync_from_cloud()

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
            for old in ["final_result.png", "error.png"]:
                if os.path.exists(old): os.remove(old)

            selected_mode = task.get('mode', '单浏览器模式 (对应脚本: simple_bypass.py)')
            script_name = task.get('script', 'katabump_renew.py')
            print(f"[*] [后台保活启动] 账号: {task.get('email')} | 脚本: {script_name}")
            
            env = os.environ.copy()
            # ✨✨✨ 物理接通核心：强制注入 CF 代理全套环境变量 ✨✨✨
            env.update({
                "EMAIL": str(task['email']), 
                "PASSWORD": str(task['password']), 
                "BYPASS_MODE": str(selected_mode), 
                "PYTHONUNBUFFERED": "1",
                "SERVER_ID": str(task.get('server_id', '177688')),
                "PROXY": str(task.get('proxy', '')),
                "RENEW_ID": str(task.get('renew_id', '')),
                # 🔥 这里是命门：物理对齐 CF 代理环境变量名
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
                subprocess.run([
                    "xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24", 
                    "python", script_name
                ], env=env, check=True)
                
                proj_name, email = script_name.replace('.py', ''), task['email']
                if os.path.exists("final_result.png"):
                    sync_to_cloud("final_result.png", f"{proj_name}/{email}.png")
                
                task['last_run'] = now.strftime("%Y-%m-%d %H:%M:%S")
                # ✨ 注入 next_run 物理字段 (同步 app.py 逻辑)
                try:
                    next_dt = now + timedelta(days=task['freq'])
                    task['next_run'] = next_dt.strftime('%Y-%m-%d %H:%M:%S')
                except: pass

                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)
                
                repo_path = str(config_path.relative_to(OUTPUT_DIR))
                sync_to_cloud(str(config_path), repo_path)
                print(f"[+] {email} 后台续期成功，云端已对齐。")

            except Exception as e:
                proj_name, email = script_name.replace('.py', ''), task['email']
                if os.path.exists("error.png"):
                    sync_to_cloud("error.png", f"{proj_name}/{email}_error.png")
                print(f"[!] {email} 后台执行失败: {e}")

if __name__ == "__main__":
    run_scheduler()
