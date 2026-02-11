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
# 1. TG 通知功能 (完全保持原样)
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    tz_bj = timezone(timedelta(hours=8))
    bj_time = datetime.now(tz_bj).strftime('%Y-%m-%d %H:%M:%S')
    emoji = "✅" if "成功" in status else "❌"
    formatted_msg = f"{emoji} **Pella 自动化续期报告**\n━━━━━━━━━━━━━━━━━━\n👤 **账户**: `{os.environ.get('EMAIL')}`\n📡 **状态**: {status}\n📝 **详情**: {message}\n🕒 **北京时间**: `{bj_time}`\n━━━━━━━━━━━━━━━━━━"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={'chat_id': chat_id, 'caption': formatted_msg, 'parse_mode': 'Markdown'}, files={'photo': f})
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={'chat_id': chat_id, 'text': formatted_msg, 'parse_mode': 'Markdown'})
    except Exception as e: logger.error(f"TG通知失败: {e}")

# ==========================================
# 2. Gmail 提取 (完全保持原样)
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
# 3. Pella 自动化流程
# ==========================================
def run_test():
    email_addr = os.environ.get("EMAIL")
    app_pw = os.environ.get("PASSWORD")
    proxy = os.environ.get("PROXY")
    ui_mode = os.environ.get("BYPASS_MODE", "SB增强模式")
    
    server_id = os.environ.get("SERVER_ID", "c216766d5bbb47fc982167ec08c144b1")
    renew_id = os.environ.get("RENEW_ID", "4j4yqfNJA")
    target_server_url = f"https://www.pella.app/server/{server_id}"
    renew_url = f"https://cuttlinks.com/{renew_id}"
    
    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None) as sb:
        try:
            # --- 第一阶段: 登录 ---
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
            sb.type('input[data-input-otp="true"]', auth_code)
            sb.sleep(10)

            # --- 第二阶段: 检查状态 ---
            sb.uc_open_with_reconnect(target_server_url, 15)
            sb.sleep(10) 
            
            def get_expiry_time_raw(sb_obj):
                try:
                    js_code = """
                    var divs = document.querySelectorAll('div');
                    for (var d of divs) {
                        var txt = d.innerText;
                        if (txt.includes('expiring') && (txt.includes('Day') || txt.includes('Hours') || txt.includes('天'))) {
                            return txt;
                        }
                    }
                    return "未找到时间文本";
                    """
                    raw_text = sb_obj.execute_script(js_code)
                    clean_text = " ".join(raw_text.split())
                    if "expiring in" in clean_text:
                        return clean_text.split("expiring in")[1].split(".")[0].strip()
                    return clean_text[:60]
                except: return "获取失败"

            expiry_before = get_expiry_time_raw(sb)
            logger.info(f"🕒 初始状态: {expiry_before}")

            target_btn = 'a[href*="tpi.li/FSfV"]'
            if sb.is_element_visible(target_btn):
                if "opacity-50" in sb.get_attribute(target_btn, "class"):
                    send_tg_notification("冷却中 🕒", f"按钮尚 in 冷却。剩余: {expiry_before}", None)
                    return 

            # --- 第三阶段: 续期网站操作 (针对点一下弹一页的广告加固) ---
            logger.info(f"📡 重新打开续期网站: {renew_url}")
            
            sb.execute_script("window.stop();")
            sb.uc_open_with_reconnect(renew_url, 20)
            sb.sleep(8)
            
            # 保存主页面的句柄
            main_window = sb.driver.current_window_handle

            for i in range(5):
                if sb.is_element_visible('button#submit-button[data-ref="first"]'):
                    sb.js_click('button#submit-button[data-ref="first"]')
                    sb.sleep(3)
                    # 针对弹窗：如果打开了新网页，循环关闭它们，直到只剩下主网页
                    if len(sb.driver.window_handles) > 1:
                        for handle in sb.driver.window_handles:
                            if handle != main_window:
                                sb.driver.switch_to.window(handle)
                                sb.driver.close()
                        sb.driver.switch_to.window(main_window)
                    if not sb.is_element_visible('button#submit-button[data-ref="first"]'): break

            # --- 算法分支 ---
            sb.sleep(6)
            try:
                current_url = sb.get_current_url()
                if "并行竞争" in ui_mode:
                    from bypass import bypass_cloudflare as api_core_1
                    api_core_1(url=current_url, proxy=proxy)
                elif "单浏览器" in ui_mode:
                    from simple_bypass import bypass_cloudflare as api_core_2
                    api_core_2(current_url, proxy=proxy)
                elif "SB增强" in ui_mode:
                    from bypass_seleniumbase import bypass_logic as api_core_4
                    api_core_4(sb)
            except Exception as e:
                logger.warning(f"破解算法执行异常: {e}")

            # 破解后也清理一次弹窗
            if len(sb.driver.window_handles) > 1:
                for handle in sb.driver.window_handles:
                    if handle != main_window:
                        sb.driver.switch_to.window(handle)
                        sb.driver.close()
                sb.driver.switch_to.window(main_window)

            captcha_btn = 'button#submit-button[data-ref="captcha"]'
            for i in range(6):
                if sb.is_element_visible(captcha_btn):
                    sb.js_click(captcha_btn)
                    sb.sleep(3)
                    # 清理点击产生的弹窗
                    if len(sb.driver.window_handles) > 1:
                        for handle in sb.driver.window_handles:
                            if handle != main_window:
                                sb.driver.switch_to.window(handle)
                                sb.driver.close()
                        sb.driver.switch_to.window(main_window)
                    if not sb.is_element_visible(captcha_btn): break

            logger.info("等待计时结束...")
            sb.sleep(18)
            final_btn = 'button#submit-button[data-ref="show"]'
            for i in range(8):
                if sb.is_element_visible(final_btn):
                    sb.js_click(final_btn)
                    sb.sleep(3)
                    # 清理点击产生的弹窗
                    if len(sb.driver.window_handles) > 1:
                        for handle in sb.driver.window_handles:
                            if handle != main_window:
                                sb.driver.switch_to.window(handle)
                                sb.driver.close()
                        sb.driver.switch_to.window(main_window)
                    if not sb.is_element_visible(final_btn): break

            # --- 第四阶段: 返回 Pella 验证结果 ---
            logger.info("操作完成，回访 Pella...")
            sb.sleep(5)
            sb.uc_open_with_reconnect(target_server_url, 15)
            sb.sleep(10)
            
            expiry_after = get_expiry_time_raw(sb)
            sb.save_screenshot("pella_final_result.png")
            
            send_tg_notification("续期成功 ✅", f"续期前: {expiry_before}\n续期后: {expiry_after}", "pella_final_result.png")

        except Exception as e:
            sb.save_screenshot("error.png")
            send_tg_notification("流程异常 ❌", f"错误详情: `{str(e)}`", "error.png")
            raise e

if __name__ == "__main__":
    run_test()
