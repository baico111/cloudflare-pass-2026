import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from seleniumbase import SB
from loguru import logger

# ==========================================
# 1. 严格按照仓库 API 逻辑进行函数导入 (完全不改)
# ==========================================
try:
    from bypass import bypass_cloudflare as api_core_1
    from simple_bypass import bypass_cloudflare as api_core_2
    from simple_bypass import bypass_parallel as api_core_3
    from bypass_seleniumbase import bypass_logic as api_core_4
    logger.info("📡 核心 API 插件已成功挂载至主程序")
except Exception as e:
    logger.error(f"🚨 API 加载失败: {e}")

# ==========================================
# 2. 高科技 TGUI 功能 (北京时间锁死 - 完全不改)
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    
    tz_bj = timezone(timedelta(hours=8))
    bj_time = datetime.now(tz_bj).strftime('%Y-%m-%d %H:%M:%S')
    emoji = "✅" if "成功" in status else "⚠️" if "未到期" in status else "❌"
    
    formatted_msg = (
        f"{emoji} **矩阵自动化续期报告**\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 **账户**: `{os.environ.get('EMAIL', 'Unknown')}`\n"
        f"📡 **状态**: {status}\n"
        f"📝 **详情**: {message}\n"
        f"🕒 **北京时间**: `{bj_time}`\n"
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
# 3. 自动化续期主流程
# ==========================================
def run_auto_renew():
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    ui_mode = os.environ.get("BYPASS_MODE", "1. 基础单次模式")
    server_id = os.environ.get("SERVER_ID", "177688")
    proxy = os.environ.get("PROXY")
    
    login_url = "https://dashboard.katabump.com/auth/login"
    target_url = f"https://dashboard.katabump.com/servers/edit?id={server_id}"
    
    # --- 唯一必须的适配：确保路径在 Docker 的 output 下 ---
    # 这能防止在 HF 环境下因权限问题无法保存截图
    OUTPUT_DIR = Path("/app/output")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None) as sb:
        try:
            # ---- [步骤 A] 登录 (完全保持你的原样) ----
            logger.info(f"🚀 正在尝试连接 Katabump 登录页: {login_url}")
            sb.uc_open_with_reconnect(login_url, 10)
            sb.type("#email", email)
            sb.type("#password", password)
            sb.click("#submit") 
            sb.sleep(6)

            # ---- [步骤 B] 跳转 (完全保持你的原样) ----
            sb.uc_open_with_reconnect(target_url, 10)
            sb.sleep(3)
            sb.js_click('button[data-bs-target="#renew-modal"]') 
            sb.sleep(6)

            # ---- [步骤 C] API 算法 (完全保持你的原样) ----
            current_url = sb.get_current_url()
            if "1." in ui_mode: result = api_core_1(current_url)
            elif "2." in ui_mode: result = api_core_2(current_url, proxy=os.environ.get("PROXY"))
            elif "3." in ui_mode: result = api_core_3(url=current_url, proxy_file="proxy.txt", batch_size=3)
            elif "4." in ui_mode: 
                api_core_4(sb)
                result = {"success": True}

            # ---- [步骤 D] 验证码与提交 (完全保持你的原样) ----
            sb.uc_gui_click_captcha()
            sb.sleep(20) 
            try:
                sb.wait_for_element_visible('#renew-modal button[type="submit"].btn-primary', timeout=20)
                sb.click('#renew-modal button[type="submit"].btn-primary')
            except:
                sb.js_click('#renew-modal button.btn-primary')
            
            sb.sleep(12) 

            # ---- [步骤 E] 结果抓取 (完全保持你的原样) ----
            sb.refresh()
            sb.wait_for_element_visible('//div[contains(text(), "Expiry")]', timeout=15)
            sb.sleep(5) 
            
            # 截图保存路径适配
            final_img = str(OUTPUT_DIR / "final_result.png")
            sb.save_screenshot(final_img)
            
            page_source = sb.get_page_source()
            
            if "2026-" in page_source:
                try:
                    expiry_date = sb.get_text('//div[contains(text(), "Expiry")]/following-sibling::div')
                    clean_date = expiry_date.strip()[:10]
                    if not clean_date.startswith("20"): raise Exception("抓取格式不符")
                    send_tg_notification("续期成功 ✅", f"服务器续期已生效！\n📅 **下次到期**: `{clean_date}`", final_img)
                except:
                    expiry_date = sb.get_text('div.card-body div.row:nth-child(4) div.col-lg-9').strip()[:10]
                    send_tg_notification("续期成功 ✅", f"服务器续期成功！\n📅 **下次到期**: `{expiry_date}`", final_img)
            else:
                send_tg_notification("未到期 ⚠️", "目前页面未刷新日期，可能尚未达到可续期时间门槛。", final_img)

        except Exception as e:
            error_img = str(OUTPUT_DIR / "error.png")
            sb.save_screenshot(error_img)
            send_tg_notification("执行异常 ❌", f"系统逻辑中断: `{str(e)}`", error_img)
            raise e

if __name__ == "__main__":
    run_auto_renew()
