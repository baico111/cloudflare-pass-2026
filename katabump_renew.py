import os
import time
from datetime import datetime
from pathlib import Path
import requests
from seleniumbase import SB
from loguru import logger

# ==========================================
# 1. 严格按照仓库 API 逻辑进行函数导入 (完全不改)
# ==========================================
try:
    # API 1: 简单模式 (bypass.py)
    from bypass import bypass_cloudflare as api_core_1
    # API 2 & 3: 完整模式 (simple_bypass.py)
    from simple_bypass import bypass_cloudflare as api_core_2
    from simple_bypass import bypass_parallel as api_core_3
    # API 4: 指纹增强模式 (bypass_seleniumbase.py)
    from bypass_seleniumbase import bypass_logic as api_core_4
    logger.info("📡 核心 API 插件已成功挂载至主程序")
except Exception as e:
    logger.error(f"🚨 API 加载失败，请检查文件层级: {e}")

# ==========================================
# 2. 高科技 TG UI 格式化功能
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    
    # 构造更美观的 TGUI
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    emoji = "✅" if "成功" in status else "⚠️" if "未到期" in status else "❌"
    
    formatted_msg = (
        f"{emoji} **矩阵自动化续期报告**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **账户**: `{os.environ.get('EMAIL', 'Unknown')}`\n"
        f"📡 **状态**: {status}\n"
        f"📝 **详情**: {message}\n"
        f"🕒 **时间**: {now}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )

    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", 
                              data={'chat_id': chat_id, 'caption': formatted_msg, 'parse_mode': 'Markdown'}, files={'photo': f})
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={'chat_id': chat_id, 'text': formatted_msg, 'parse_mode': 'Markdown'})
    except Exception as e: logger.error(f"TG通知失败: {e}")

# ==========================================
# 3. 自动化续期主流程 (逻辑增强版)
# ==========================================
def run_auto_renew():
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    ui_mode = os.environ.get("BYPASS_MODE", "1. 基础单次模式")
    
    login_url = "https://dashboard.katabump.com/auth/login"
    target_url = "https://dashboard.katabump.com/servers/edit?id=177688"
    OUTPUT_DIR = Path("/app/output")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with SB(uc=True, xvfb=True) as sb:
        try:
            # ---- [步骤 A] 主流程登录 ----
            sb.uc_open_with_reconnect(login_url, 10)
            sb.type("#email", email)
            sb.type("#password", password)
            sb.click("#submit") # 匹配 id="submit"
            sb.sleep(6)

            # ---- [步骤 B] 跳转至 Renew 页面 ----
            sb.uc_open_with_reconnect(target_url, 10)
            sb.sleep(3)
            sb.js_click('button[data-bs-target="#renew-modal"]') # 触发验证弹窗
            sb.sleep(6)

            # ---- [步骤 C] 核心：API 调用 (保持原逻辑) ----
            current_url = sb.get_current_url()
            logger.info(f">>> 正在按原作者逻辑调用 API: {ui_mode}")

            if "1." in ui_mode:
                result = api_core_1(current_url)
            elif "2." in ui_mode:
                result = api_core_2(current_url, proxy=os.environ.get("PROXY"))
            elif "3." in ui_mode:
                result = api_core_3(url=current_url, proxy_file="proxy.txt", batch_size=3)
            elif "4." in ui_mode:
                api_core_4(sb)
                result = {"success": True}

            # ---- [步骤 D] 整合成果与提交 (精准修复可见性问题) ----
            sb.uc_gui_click_captcha()
            logger.info("验证已完成，进入 20 秒脚本启动与稳定缓冲期...")
            sb.sleep(20) 
            
            # 修复：增加 wait_for_element_visible 确保按钮完全渲染并显示
            logger.info("正在等待 Renew 提交按钮进入可见状态...")
            try:
                # 将等待时间从默认的 7 秒手动提升，并确保元素 visible
                sb.wait_for_element_visible('button[type="submit"].btn-primary', timeout=30)
                sb.click('button[type="submit"].btn-primary')
                logger.info("执行最终 Renew 提交点击成功")
            except Exception as e:
                logger.warning(f"常规点击失败，尝试使用 JS 强制穿透点击: {e}")
                sb.js_click('button[type="submit"].btn-primary') # 最后的兜底方案
            
            sb.sleep(10) # 等待结果反馈加载

            # ---- [步骤 E] 结果捕获与智能通知 ----
            final_img = str(OUTPUT_DIR / "final_result.png")
            sb.save_screenshot(final_img)
            
            # 获取页面文字内容判断状态
            page_text = sb.get_page_source()
            
            if "2026-" in page_text:
                # 抓取到期时间：<div class="col-lg-9 col-md-8">2026-02-02</div>
                try:
                    expiry_date = sb.get_text('div.col-lg-9.col-md-8')
                    send_tg_notification("续期成功 ✅", f"服务器已成功续命！\n📅 **下次到期**: `{expiry_date}`", final_img)
                except:
                    send_tg_notification("续期成功 ✅", "续期已完成，但未抓取到具体日期。", final_img)
            else:
                # 判定为还没到续期时间
                send_tg_notification("未到期 ⚠️", "目前尚未达到可续期的时间点，请稍后再试。", final_img)

        except Exception as e:
            error_img = str(OUTPUT_DIR / "error.png")
            sb.save_screenshot(error_img)
            send_tg_notification("执行异常 ❌", f"错误详情: `{str(e)}`", error_img)
            raise e

if __name__ == "__main__":
    run_auto_renew()
