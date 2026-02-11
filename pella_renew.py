import os
import time
import imaplib
import email
import re
import requests
from datetime import datetime, timedelta, timezone
from seleniumbase import SB
from loguru import logger

# ==========================================
# 1. TG 通知功能 (保持不变)
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    tz_bj = timezone(timedelta(hours=8))
    bj_time = datetime.now(tz_bj).strftime('%Y-%m-%d %H:%M:%S')
    email_user = os.environ.get('EMAIL')
    emoji = "✅" if "成功" in status else "❌"
    formatted_msg = f"{emoji} **Pella 自动化续期报告**\n━━━━━━━━━━━━━━━━━━\n👤 **账户**: `{email_user}`\n📡 **状态**: {status}\n📝 **详情**: {message}\n🕒 **北京时间**: `{bj_time}`\n━━━━━━━━━━━━━━━━━━"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={'chat_id': chat_id, 'caption': formatted_msg, 'parse_mode': 'Markdown'}, files={'photo': f})
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={'chat_id': chat_id, 'text': formatted_msg, 'parse_mode': 'Markdown'})
    except Exception as e: logger.error(f"TG通知失败: {e}")

# ==========================================
# 2. Gmail 提取 (保持不变)
# ==========================================
def get_pella_code(mail_address, app_password):
    logger.info("📡 正在连接 Gmail 抓取验证码...")
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(mail_address, app_password)
        mail.select("inbox")
        for i in range(10):
            status, messages = mail.search(None, '(FROM "Pella" UNSEEN)')
            if status == "OK" and messages[0]:
                latest_msg_id = messages[0].split()[-1]
                status, data = mail.fetch(latest_msg_id, "(RFC822)")
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)
                content = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            content = part.get_payload(decode=True).decode()
                else:
                    content = msg.get_payload(decode=True).decode()
                code = re.search(r'\b\d{6}\b', content)
                if code:
                    mail.store(latest_msg_id, '+FLAGS', '\\Seen')
                    return code.group()
            time.sleep(10)
        return None
    except Exception as e: return None

# ==========================================
# 3. Pella 自动化流程 (内存深度重置版)
# ==========================================
def run_test():
    email_addr = os.environ.get("EMAIL")
    app_pw = os.environ.get("PASSWORD")
    proxy = os.environ.get("PROXY")
    ui_mode = os.environ.get("BYPASS_MODE", "单浏览器模式")
    server_id = os.environ.get("SERVER_ID", "c216766d5bbb47fc982167ec08c144b1")
    renew_id = os.environ.get("RENEW_ID", "4j4yqfNJA")
    
    target_server_url = f"https://www.pella.app/server/{server_id}"
    renew_url = f"https://cuttlinks.com/{renew_id}"
    
    expiry_before = "未知"

    # --- 第一阶段: 登录与检查时长 ---
    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None, block_images=True) as sb:
        try:
            logger.info("🚀 [面板监控] 正在打开 Pella 登录页面...")
            sb.uc_open_with_reconnect("https://www.pella.app/login", 20)
            sb.sleep(5)
            sb.uc_gui_click_captcha()
            sb.wait_for_element_visible("#identifier-field", timeout=60)
            
            for char in email_addr:
                sb.add_text("#identifier-field", char)
                time.sleep(0.1)
            sb.press_keys("#identifier-field", "\n")
            sb.sleep(5)
            
            auth_code = get_pella_code(email_addr, app_pw)
            if not auth_code: raise Exception("验证码抓取失败")
            logger.info(f"🔑 [面板监控] 成功获取验证码: {auth_code}")
            sb.type('input[data-input-otp="true"]', auth_code)
            sb.sleep(10)

            sb.uc_open_with_reconnect(target_server_url, 15)
            sb.sleep(10) 
            
            def get_expiry_time_raw(sb_obj):
                try:
                    js_code = "var divs = document.querySelectorAll('div'); for (var d of divs) { var txt = d.innerText; if (txt.includes('expiring') && (txt.includes('Day') || txt.includes('Hours'))) { return txt; } } return '未找到';"
                    raw_text = sb_obj.execute_script(js_code)
                    clean_text = " ".join(raw_text.split())
                    if "expiring in" in clean_text: return clean_text.split("expiring in")[1].split(".")[0].strip()
                    return clean_text[:60]
                except: return "获取失败"

            expiry_before = get_expiry_time_raw(sb)
            logger.info(f"🕒 [面板监控] 续期前时长: {expiry_before}")
            
            # 第一阶段结束，主动退出 SB 以释放全部物理内存
            logger.info("🧹 [物理加固] 正在重置浏览器实例以清理内存...")
        except Exception as e:
            sb.save_screenshot("error_stage1.png")
            send_tg_notification("登录异常 ❌", f"详情: `{str(e)}`", "error_stage1.png")
            return

    # --- 第二阶段: 纯净环境跳转续期页 ---
    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None, block_images=True) as sb:
        try:
            logger.info(f"🚀 [面板监控] 使用全新实例跳转至续期站: {renew_url}")
            
            # 物理加固：拦截所有多媒体资源，只留文字和点击逻辑
            try:
                sb.execute_cdp_cmd("Network.setBlockedURLs", {"urls": ["*google*", "*ads*", "*.mp4", "*.webm", "*.jpg", "*.png"]})
                sb.execute_cdp_cmd("Network.enable", {})
                sb.driver.set_page_load_timeout(20)
                sb.open(renew_url)
            except:
                sb.execute_script("window.stop();")
            
            sb.sleep(5)
            main_window = sb.driver.current_window_handle

            for i in range(5):
                logger.info(f"🖱️ [面板监控] 检测 [First] 按钮 (第 {i+1} 次)...")
                if sb.is_element_visible('button#submit-button[data-ref="first"]'):
                    sb.execute_script("document.querySelector('button#submit-button[data-ref=\"first\"]').click();")
                    sb.sleep(3)
                    # 物理关窗
                    if len(sb.driver.window_handles) > 1:
                        for h in sb.driver.window_handles:
                            if h != main_window:
                                try: sb.driver.switch_to.window(h); sb.driver.close()
                                except: pass
                        sb.driver.switch_to.window(main_window)
                    if not sb.is_element_visible('button#submit-button[data-ref="first"]'): break
                sb.sleep(2)

            # --- 算法分支 ---
            sb.sleep(6)
            current_url = sb.get_current_url()
            if "并行竞争" in ui_mode:
                from bypass import bypass_cloudflare
                bypass_cloudflare(url=current_url, proxy=proxy)
            elif "单浏览器" in ui_mode:
                from simple_bypass import bypass_cloudflare
                bypass_cloudflare(current_url, proxy=proxy)
            elif "SB增强" in ui_mode:
                from bypass_seleniumbase import bypass_logic
                bypass_logic(sb)

            # 后续点击
            for btn_ref in ["captcha", "show"]:
                selector = f'button#submit-button[data-ref="{btn_ref}"]'
                for i in range(8):
                    if sb.is_element_visible(selector):
                        sb.execute_script(f"document.querySelector('{selector}').click();")
                        sb.sleep(3)
                        if len(sb.driver.window_handles) > 1:
                            for h in sb.driver.window_handles:
                                if h != main_window:
                                    try: sb.driver.switch_to.window(h); sb.driver.close()
                                    except: pass
                            sb.driver.switch_to.window(main_window)
                        if not sb.is_element_visible(selector): break
                if btn_ref == "captcha": sb.sleep(18)

            # --- 第三阶段: 最终验证 ---
            # 同样重开或清理后再回访
            sb.uc_open_with_reconnect(target_server_url, 15)
            sb.sleep(10)
            expiry_after = get_expiry_time_raw(sb)
            sb.save_screenshot("pella_final_result.png")
            send_tg_notification("成功 ✅", f"前: {expiry_before}\n后: {expiry_after}", "pella_final_result.png")

        except Exception as e:
            logger.error(f"🔥 [面板监控] 最终阶段崩溃: {str(e)}")
            sb.save_screenshot("error_final.png")
            send_tg_notification("续期异常 ❌", f"详情: `{str(e)}`", "error_final.png")
            raise e

if __name__ == "__main__":
    run_test()
