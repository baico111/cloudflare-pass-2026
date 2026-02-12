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
# 1. TG 通知功能 (保持原样)
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
# 2. Gmail 验证码提取 (保持原样)
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
# 3. 辅助功能：JS 抓取时间
# ==========================================
def get_expiry_time_raw(sb_obj):
    js_time_grabber = """
    var divs = document.querySelectorAll('div');
    for (var d of divs) {
        var txt = d.innerText;
        if (txt.includes('expiring') && (txt.includes('Day') || txt.includes('Hours') || txt.includes('Hour') || txt.includes('天'))) {
            return txt;
        }
    }
    return "未找到时间文本";
    """
    try:
        return sb_obj.execute_script(js_time_grabber)
    except:
        return "抓取失败"

# ==========================================
# 4. Pella 自动化流程 (严格遵循你的七阶段逻辑)
# ==========================================
def run_test():
    email_addr = os.environ.get("PELLA_EMAIL")
    app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    server_id = os.environ.get("SERVER_ID", "2b3bbeef0eeb452299a11e431c3c2d5b")
    renew_id = os.environ.get("RENEW_ID", "m4w0wJrEmgEC")
    proxy = os.environ.get("PROXY")
    
    target_server_url = f"https://www.pella.app/server/{server_id}"
    renew_url = f"https://cuty.io/{renew_id}"
    output_img = "/app/output/final_result.png"

    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None,
            chromium_arg="--blink-settings=imagesEnabled=false,--mute-audio") as sb:
        try:
            # --- 第一阶段: 登录 ---
            logger.info("🚀 [登录] 正在进入 Pella...")
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

            # --- 第二阶段: 记录续期前时间 ---
            sb.uc_open_with_reconnect(target_server_url, 10)
            sb.sleep(10)
            expiry_before = get_expiry_time_raw(sb)
            logger.info(f"🕒 [面板监控] 续期前时间: {expiry_before}")

            # --- 第三阶段: 进入续期网站点击第一个 Continue ---
            logger.info(f"🚀 [面板监控] 跳转至续期网站: {renew_url}")
            sb.uc_open_with_reconnect(renew_url, 10)
            sb.sleep(5)
            
            logger.info("🖱️ [面板监控] 执行第一个 Continue 强力点击...")
            for i in range(5):
                try:
                    if sb.is_element_visible('button#submit-button[data-ref="first"]'):
                        sb.js_click('button#submit-button[data-ref="first"]')
                        sb.sleep(3)
                        if len(sb.driver.window_handles) > 1:
                            sb.driver.switch_to.window(sb.driver.window_handles[0])
                        if not sb.is_element_visible('button#submit-button[data-ref="first"]'):
                            break
                except: pass

            # --- 第四阶段: 处理 Cloudflare 人机挑战 (Kata 模式) ---
            logger.info("🛡️ [面板监控] 检测人机验证中...")
            sb.sleep(5)
            try:
                cf_iframe = 'iframe[src*="cloudflare"]'
                if sb.is_element_visible(cf_iframe):
                    logger.info("✅ [面板监控] 发现 CF 验证，尝试 Kata 模式穿透...")
                    sb.switch_to_frame(cf_iframe)
                    sb.click('span.mark') 
                    sb.switch_to_parent_frame()
                    sb.sleep(6)
                else:
                    sb.uc_gui_click_captcha()
            except: pass

            # --- 第五阶段: 强力点击 "I am not a robot" ---
            logger.info("🖱️ [面板监控] 开始点击 'I am not a robot' (data-ref='captcha')...")
            captcha_btn = 'button#submit-button[data-ref="captcha"]'
            for i in range(8): 
                try:
                    if sb.is_element_visible(captcha_btn):
                        sb.js_click(captcha_btn)
                        sb.sleep(3)
                        if len(sb.driver.window_handles) > 1:
                            curr = sb.driver.current_window_handle
                            for handle in sb.driver.window_handles:
                                if handle != curr:
                                    sb.driver.switch_to.window(handle)
                                    sb.driver.close()
                            sb.driver.switch_to.window(sb.driver.window_handles[0])
                        if not sb.is_element_visible(captcha_btn):
                            break
                except: pass

            # --- 第六阶段: 等待 计时并点击最终 Go 按钮 ---
            logger.info("⌛ [面板监控] 等待 18 秒计时结束...")
            sb.sleep(18)
            
            final_btn = 'button#submit-button[data-ref="show"]'
            click_final = False
            for i in range(8):
                try:
                    if sb.is_element_visible(final_btn):
                        logger.info(f"🖱️ [面板监控] 第 {i+1} 次点击最终 Go 按钮...")
                        sb.js_click(final_btn)
                        sb.sleep(3)
                        if len(sb.driver.window_handles) > 1:
                            curr = sb.driver.current_window_handle
                            for h in sb.driver.window_handles:
                                if h != curr: sb.driver.switch_to.window(h); sb.driver.close()
                            sb.driver.switch_to.window(sb.driver.window_handles[0])
                        
                        if not sb.is_element_visible(final_btn):
                            click_final = True
                            break
                except: pass
            
            # --- 第七阶段: 结果验证 (使用指定 JS 逻辑) ---
            logger.info("🏁 [面板监控] 操作完成，正在回访 Pella 验证续期结果...")
            sb.sleep(5)
            sb.uc_open_with_reconnect(target_server_url, 10)
            sb.sleep(10)
            
            expiry_after = get_expiry_time_raw(sb)
            logger.info(f"🕒 [面板监控] 续期后剩余时间: {expiry_after}")
            
            # 适配 HF 路径
            sb.save_screenshot(output_img)
            
            if click_final:
                print("PELLA_SUCCESS_FLAG")
                send_tg_notification("续期成功 ✅", f"续期前: {expiry_before}\n续期后: {expiry_after}", output_img)
            else:
                send_tg_notification("操作反馈 ⚠️", f"流程已执行至最后，请检查截图。续期前: {expiry_before}\n当前时间: {expiry_after}", output_img)

        except Exception as e:
            logger.error(f"🔥 [崩溃]: {str(e)}")
            send_tg_notification("保活失败 ❌", f"报错: `{str(e)}`", None)
            raise e

if __name__ == "__main__":
    run_test()
