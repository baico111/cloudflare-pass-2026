import json
import os
import subprocess
from datetime import datetime, timedelta

CONFIG_FILE = "/app/output/tasks_config.json" # 读取持久化存储中的配置

def run_scheduler():
    if not os.path.exists(CONFIG_FILE):
        print("[*] 配置文件不存在，跳过自动检查。")
        return

    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        tasks = json.load(f)

    now = datetime.now()
    updated = False

    for task in tasks:
        if not task.get('active', True): continue
        
        # 核心逻辑：检查是否到期
        last_run_str = task.get('last_run')
        freq = task.get('freq', 3) # 读取 UI 填写的周期
        
        should_run = False
        if not last_run_str:
            should_run = True # 从未运行，立即运行
        else:
            last_run_time = datetime.strptime(last_run_str, "%Y-%m-%d %H:%M:%S")
            if now >= (last_run_time + timedelta(days=freq)):
                should_run = True

        if should_run:
            print(f"[*] 自动执行任务: {task['name']}")
            env = os.environ.copy()
            env["EMAIL"] = task['email']     # 注入 UI 填写的账号
            env["PASSWORD"] = task['password'] # 注入 UI 填写的密码
            
            try:
                # 运行对应的续期脚本
                subprocess.run(["xvfb-run", "--server-args=-screen 0 1920x1080x24", "python", task['script']], env=env, check=True)
                task['last_run'] = now.strftime("%Y-%m-%d %H:%M:%S")
                updated = True
            except Exception as e:
                print(f"[!] {task['name']} 失败: {e}")

    if updated:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    run_scheduler()
