import os
import time
import random
from datetime import datetime
from pathlib import Path
import requests
from seleniumbase import SB
from loguru import logger # 使用你要求的 loguru 进行日志管理

# --- 核心集成：按照仓库提供的函数式方式导入 ---
try:
    # 这里的导入对应你仓库中的文件名
    from simple_bypass import bypass_cloudflare as simple_logic
    from bypass import bypass_cloudflare as parallel_logic
    from bypass_seleniumbase import bypass_logic as enhanced_logic
    logger.info("成功从外部脚本导入绕过函数")
except ImportError as e:
    logger.error(f"模块导入失败，请确保脚本文件在根目录: {e}")

def send_tg_notification(message, photo_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", 
                              data={'chat_id': chat_id, 'caption': message}, files={'photo': f})
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={'chat_id': chat_id, 'text': message})
    except Exception as e: logger.error(f"TG通知失败: {e}")

def run_auto_renew():
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    ui_mode = os.environ.get("BYPASS_MODE", "SB增强模式")
    
    # 你指定的 2026-01-29 最新流程地址
    login_url = "https://dashboard.katabump.com/auth/login"
    target_url = "https://dashboard.katabump.com/servers/edit?id=177688"
    OUTPUT_DIR = Path("/app/output")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    logger.info(f"启动 Katabump 自动续期流程 | 模式: {ui_mode}")

    # 使用集成了 UC 模式的浏览器实例
    with SB(uc=True, xvfb=True) as sb:
        try:
            # ---- 1. 登录流程 (匹配你的截图) ----
            logger.info("步骤 1/5: 正在登录...")
            sb.uc_open_with_reconnect(login_url, 10)
            sb.wait_for_element("#email", timeout=20)
            sb.type("#email", email)
            sb.type("#password", password)
            sb.click("#submit") # 点击 id="submit" 的按钮
            sb.sleep(6)

            # ---- 2. 进入 See 页面 ----
            logger.info("步骤 2/5: 跳转至服务器管理页...")
            sb.uc_open_with_reconnect(target_url, 10)
            sb.sleep(3)

            # ---- 3. 触发 Renew 弹窗 ----
            logger.info("步骤 3/5: 点击 Renew 触发验证弹窗...")
            sb.scroll_to('button[data-bs-target="#renew-modal"]')
            sb.js_click('button[data-bs-target="#renew-modal"]') # 强力 JS 点击
            sb.sleep(5) 

            # ---- 4. 关键：按照仓库工作方式调用函数 ----
            current_url = sb.get_current_url()
            logger.info(f"步骤 4/5: 弹窗已出，正在调用仓库函数进行绕过...")
            
            # 存证截图
            sb.save_screenshot(str(OUTPUT_DIR / "before_bypass.png"))

            if "增强" in ui_mode:
                # 调用 bypass_seleniumbase.py 的核心函数
                enhanced_logic(sb) 
            elif "竞争" in ui_mode:
                # 按照你给出的示例：调用 bypass.py 的并行逻辑
                parallel_logic(current_url) 
            else:
                # 调用 simple_bypass.py 的单次绕过逻辑
                simple_logic(current_url)

            # 无论调用哪个函数，最后由主程序执行物理点击过盾
            sb.uc_gui_click_captcha() 
            sb.sleep(5)
            sb.save_screenshot(str(OUTPUT_DIR / "after_bypass.png"))
            logger.success("人机验证环节执行完毕")

            # ---- 5. 最终确认 ----
            logger.info("步骤 5/5: 点击最终更新...")
            sb.click('//button[contains(., "更新")]')
            sb.sleep(8)

            # 成功反馈
            success_img = str(OUTPUT_DIR / "success.png")
            sb.save_screenshot(success_img)
            msg = f"✅ [{datetime.now().strftime('%H:%M')}] 自动续期成功！使用逻辑: {ui_mode}"
            logger.info(msg)
            send_tg_notification(msg, success_img)

        except Exception as e:
            error_img = str(OUTPUT_DIR / "error.png")
            sb.save_screenshot(error_img)
            logger.error(f"同步失败: {str(e)}")
            send_tg_notification(f"❌ 续期任务中断\n错误原因: {str(e)}", error_img)
            raise e

if __name__ == "__main__":
    run_auto_renew()
