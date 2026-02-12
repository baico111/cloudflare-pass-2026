import os
import time
import imaplib
import email
import re
import requests
import sys
from datetime import datetime, timedelta, timezone
from seleniumbase import SB
from loguru import logger

# ==========================================
# 1. TG 通知功能 (锁死不改)
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    tz_bj = timezone(timedelta(hours=8))
    bj_time = datetime.now(tz_bj).strftime('%Y-%m-%d %H:%M:%S')
    emoji = "✅" if "成功" in status else "❌"
    formatted_msg = f"{emoji} **Pella 自动化续期报告**\n━━━━━━━━━━━━━━━━━━\n👤 **账户**: `{os.environ.get('PELLA_EMAIL')}`\n📡 **状态**: {status}\n📝 : {message}\n🕒 **北京时间**: `{bj_time}`\n━━━━━━━━━━━━━━━━━━"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", data={'chat_id': chat_id, 'caption': formatted_msg, 'parse_mode': 'Markdown'}, files={'photo': f})
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={'chat_id': chat_id, 'text': formatted_msg, 'parse_mode': 'Markdown'})
    except Exception as e: logger.error(f"TG通知失败: {e}")

# ==========================================
# 2. Gmail 验证码提取 (锁死不改)
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
# 3. Pella 自动化流程 (重构版：先时间后状态)
# ==========================================
def run_test():
    email_addr = os.environ.get("PELLA_EMAIL")
    app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    server_id = os.environ.get("SERVER_ID", "2b3bbeef0eeb452299a11e431c3c2d5b")
    renew_id = os.environ.get("RENEW_ID", "m4w0wJrEmgEC")
    proxy = os.environ.get("PROXY")
    
    target_server_url = f"https://www.pella.app/server/{server_id}"
    renew_url = f"https://cuty.io/{renew_id}"
    
    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None) as sb:
        try:
            # --- 第一阶段: 登录流程 ---
            logger.info("🚀 [面板监控] 正在启动 Pella 登录流程...")
            sb.uc_open_with_reconnect("https://www.pella.app/login", 10)
            sb.sleep(5)
            sb.uc_gui_click_captcha()
            sb.wait_for_element_visible("#identifier-field", timeout=25)
            for char in email_addr:
                sb.add_text("#identifier-field", char)
                time.sleep(0.1)
            sb.press_keys("#identifier-field", "\n")
            sb.sleep(5)
            auth_code = get_pella_code(email_addr, app_pw)
            if not auth_code: raise Exception("验证码抓取失败")
            sb.type('input[data-input-otp="true"]', auth_code)
            sb.sleep(10)

            # --- 第二阶段: 数据抓取与状态判定 ---
            logger.info("🔍 [面板监控] 正在回访面板执行数据抓取...")
            sb.uc_open_with_reconnect(target_server_url, 10)
            sb.sleep(10) 

            # 【指令修正】：先提取续期前的时间
            def get_expiry_time_raw(sb_obj):
                try:
                    js_time_code = """
                    var divs = document.querySelectorAll('div');
                    for (var d of divs) {
                        var txt = d.innerText;
                        if (txt.includes('expiring') && (txt.includes('Day') || txt.includes('Hours') || txt.includes('天'))) {
                            return txt;
                        }
                    }
                    return "未找到时间文本";
                    """
                    raw_text = sb_obj.execute_script(js_time_code)
                    clean_text = " ".join(raw_text.split())
                    if "expiring in" in clean_text:
                        return clean_text.split("expiring in")[1].split(".")[0].strip()
                    return clean_text[:60]
                except: return "获取失败"

            expiry_before = get_expiry_time_raw(sb)
            logger.info(f"🕒 [面板监控] 续期前剩余时间: {expiry_before}")

            # 【指令修正】：抓完时间后，紧接着进行状态判定
            js_status_code = f"""
            (function() {{
                var btn = document.querySelector('a[href*="{renew_id}"]');
                if (btn) {{
                    var is_disabled = btn.classList.contains('pointer-events-none') || 
                                     btn.classList.contains('opacity-50');
                    return !is_disabled; // 返回是否高亮
                }}
                return false;
            }})();
            """
            is_highlighted = sb.execute_script(js_status_code)
            logger.info(f"💡 [按钮检测] 当前高亮状态: {is_highlighted}")

            # 熔断逻辑：如果没亮，发送通知并直接退出，不更新调度时间
            if not is_highlighted:
                logger.warning("🕒 [面板监控] 检测到按钮处于冷却中，终止流程。")
                send_tg_notification("保活报告 (冷却中) 🕒", f"按钮尚未高亮。本次不更新运行时间。剩余时间: {expiry_before}", None)
                sys.exit(0)

            # --- 第三阶段: 续期执行 (全功能补完) ---
            logger.info(f"🚀 [面板监控] 跳转续期网站: {renew_url}")
            sb.uc_open_with_reconnect(renew_url, 10)
            sb.sleep(5)
            
            # A. 点击第一个 Continue
            for i in range(5):
                try:
                    if sb.is_element_visible('button#submit-button[data-ref="first"]'):
                        sb.js_click('button#submit-button[data-ref="first"]')
                        sb.sleep(3)
                        if len(sb.driver.window_handles) > 1:
                            main_h = sb.driver.window_handles[0]
                            for h in sb.driver.window_handles:
                                if h != main_h: sb.driver.switch_to.window(h); sb.driver.close()
                            sb.driver.switch_to.window(main_h)
                        if not sb.is_element_visible('button#submit-button[data-ref="first"]'): break
                except: pass

            # B. 处理 CF
            sb.sleep(5)
            try:
                cf_iframe = 'iframe[src*="cloudflare"]'
                if sb.is_element_visible(cf_iframe):
                    sb.switch_to_frame(cf_iframe)
                    sb.click('span.mark') 
                    sb.switch_to_parent_frame()
                    sb.sleep(6)
            except: pass

            # C. 点击 I am not a robot
            captcha_btn = 'button#submit-button[data-ref="captcha"]'
            for i in range(8): 
                try:
                    if sb.is_element_visible(captcha_btn):
                        sb.js_click(captcha_btn)
                        sb.sleep(3)
                        if len(sb.driver.window_handles) > 1:
                            main_h = sb.driver.window_handles[0]
                            for h in sb.driver.window_handles:
                                if h != main_h: sb.driver.switch_to.window(h); sb.driver.close()
                            sb.driver.switch_to.window(main_h)
                        if not sb.is_element_visible(captcha_btn): break
                except: pass

            # D. 等待并点击最终 Go
            sb.sleep(18)
            final_btn = 'button#submit-button[data-ref="show"]'
            click_final = False
            for i in range(8):
                try:
                    if sb.is_element_visible(final_btn):
                        sb.js_click(final_btn)
                        sb.sleep(3)
                        if len(sb.driver.window_handles) > 1:
                            main_h = sb.driver.window_handles[0]
                            for h in sb.driver.window_handles:
                                if h != main_h: sb.driver.switch_to.window(h); sb.driver.close()
                            sb.driver.switch_to.window(main_h)
                        if not sb.is_element_visible(final_btn):
                            click_final = True
                            break
                except: pass
            
            # --- 第四阶段: 结果验证 ---
            sb.sleep(5)
            sb.uc_open_with_reconnect(target_server_url, 10)
            sb.sleep(10)
            expiry_after = get_expiry_time_raw(sb)
            logger.info(f"🕒 [面板监控] 续期后剩余时间: {expiry_after}")
            sb.save_screenshot("final_result.png")
            
            if click_final:
                print("PELLA_SUCCESS_FLAG") # 唯一触发更新标记
                send_tg_notification("续期成功 ✅", f"续期前: {expiry_before}\n续期后: {expiry_after}", "final_result.png")
            else:
                send_tg_notification("操作反馈 ⚠️", f"流程已结束，请检查截图。前: {expiry_before}\n当前: {expiry_after}", "final_result.png")

        except Exception as e:
            logger.error(f"🔥 [面板监控] 流程崩溃: {str(e)}")
            send_tg_notification("保活失败 ❌", f"错误: `{str(e)}`", None)
            raise e

if __name__ == "__main__":
    run_test()
