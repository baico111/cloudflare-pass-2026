import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

# 配置文件路径，必须与 app.py 保持一致
CONFIG_FILE = "/app/output/tasks_config.json"

def run_scheduler():
    if not os.path.exists(CONFIG_FILE):
        print("[*] 尚未配置任何任务，调度器进入待命状态。")
        return

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            tasks = json.load(f)
    except Exception as e:
        print(f"[!] 读取配置文件失败: {e}")
        return

    # --- 核心锁定：强制使用北京时间 (UTC+8) ---
    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz)
    updated = False

    for task in tasks:
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
                print(f"[!] 检测到无效的时间记录 '{last_run_str}'，正在强制触发以修复数据...")
                should_run = True

        if should_run:
            selected_mode = task.get('mode', '单浏览器模式 (对应脚本: simple_bypass.py)')
            script_name = task.get('script', 'katabump_renew.py')
            print(f"[*] [周期任务启动] 项目: {task['name']} | 脚本: {script_name} | 挂载 API: {selected_mode}")
            
            env = os.environ.copy()
            env["EMAIL"] = task['email']
            env["PASSWORD"] = task['password']
            env["BYPASS_MODE"] = selected_mode 
            env["PYTHONUNBUFFERED"] = "1"
            env["SERVER_ID"] = str(task.get('server_id', ''))
            env["PROXY"] = task.get('proxy', '')
            env["RENEW_ID"] = task.get('renew_id', '')
            
            # 为 Pella 专项脚本映射特定变量
            if script_name == "pella_renew.py":
                env["PELLA_EMAIL"] = task['email']
                env["GMAIL_APP_PASSWORD"] = task['password']
            
            if script_name == "luneshost.py":
                env["STAY_TIME"] = str(task.get('stay_time', 10))
                env["REFRESH_COUNT"] = str(task.get('refresh_count', 3))
                env["REFRESH_INTERVAL"] = str(task.get('refresh_interval', 5))
            
            try:
                subprocess.run([
                    "xvfb-run", "-a", "--server-args=-screen 0 1920x1080x24", 
                    "python", script_name
                ], env=env, check=True)
                
                task['last_run'] = now.strftime("%Y-%m-%d %H:%M:%S")
                updated = True
                print(f"[+] {task['name']} 自动同步成功。")
            except Exception as e:
                print(f"[!] {task['name']} 自动执行失败: {e}")

    if updated:
        try:
            temp_file = CONFIG_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(tasks, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, CONFIG_FILE)
            print("[*] 任务配置已同步更新。")
        except Exception as e:
            print(f"[!] 写入配置文件失败: {e}")

if __name__ == "__main__":
    run_scheduler()
