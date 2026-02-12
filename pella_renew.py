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
    # 注意：此处维持 PELLA_EMAIL 环境变量读取逻辑
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
# 3. 辅助功能：数值换算、弹窗强杀、盾牌拆除 (锁死不改)
# ==========================================
def parse_time_to_hours(text):
    if not text or "未找到" in text: return 0
    try:
        total_hours = 0
        days = re.search(r'(\d+)\s*Day', text, re.I)
        hours = re.search(r'(\d+)\s*(?:Hour|h|Minute|M)', text, re.I)
        if days: total_hours += int(days.group(1)) * 24
        if hours: total_hours += int(hours.group(1))
        return total_hours
    except: return 0

def handle_ad_windows(sb_obj):
    try:
        handles = sb_obj.driver.window_handles
        if len(handles) > 1:
            main_h = handles[0]
            for h in handles[1:]:
                sb_obj.driver.switch_to.window(h)
                sb_obj.driver.close()
            sb_obj.driver.switch_to.window(main_h)
            return True
    except: pass
    return False

def clean_overlays(sb_obj):
    """
    暴力删除拦截点击的透明层 (解决 element click intercepted 报错)
    """
    try:
        js_cleanup = """
        var divs = document.querySelectorAll('div');
        for (var i = 0; i < divs.length; i++) {
            var style = window.getComputedStyle(divs[i]);
            var zIndex = parseInt(style.zIndex);
            if (zIndex > 1000 || style.position === 'fixed') {
                divs[i].remove();
            }
        }
        """
        sb_obj.execute_script(js_cleanup)
        logger.info("🧹 [清场] 已清理隐形拦截层")
    except: pass

# ==========================================
# 4. Pella 自动化流程
# ==========================================
def run_test():
    email_addr = os.environ.get("PELLA_EMAIL")
    app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    server_id = os.environ.get("SERVER_ID", "2b3bbeef0eeb452299a11e431c3c2d5b")
    renew_id = os.environ.get("RENEW_ID", "m4w0wJrEmgEC")
    proxy = os.environ.get("PROXY")
    
    target_server_url = f"https://www.pella.app/server/{server_id}"
    renew_url = f"https://cuty.io/{renew_id}"
    
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

    # 极简启动环境：禁图禁音
    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None,
            chromium_arg="--blink-settings=imagesEnabled=false,--mute-audio") as sb:
        try:
            # --- 阶段 1: 登录 ---
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

            # --- 阶段 2: 记录续期前时间 ---
            sb.uc_open_with_reconnect(target_server_url, 10)
            sb.sleep(10)
            text_before = sb.execute_script(js_time_grabber)
            hours_before = parse_time_to_hours(text_before)
            logger.info(f"🕒 [续期前] 原始: {text_before} | 小时: {hours_before}")

            # --- 阶段 3: 执行续期 (点-清-关 闭环) ---
            logger.info(f"🚀 [跳转] 进入续期网站: {renew_url}")
            sb.uc_open_with_reconnect(renew_url, 10)
            sb.sleep(5)
            handle_ad_windows(sb)

            # [A] 第一个 Continue
            for i in range(10):
                if sb.is_element_visible('button#submit-button[data-ref="first"]'):
                    clean_overlays(sb) # 点击前先清场
                    try:
                        sb.click('button#submit-button[data-ref="first"]') # 普通点击
                        sb.sleep(3)
                        if handle_ad_windows(sb): continue
                        if not sb.is_element_visible('button#submit-button[data-ref="first"]'): break
                    except:
                        handle_ad_windows(sb)
                        continue

            # [B] 处理 CF (维持原样)
            sb.sleep(5)
            handle_ad_windows(sb)
            try:
                cf_iframe = 'iframe[src*="cloudflare"]'
                if sb.is_element_visible(cf_iframe):
                    sb.switch_to_frame(cf_iframe)
                    sb.click('span.mark') 
                    sb.switch_to_parent_frame()
                    sb.sleep(6)
            except: pass

            # [C] Robot 点击
            captcha_btn = 'button#submit-button[data-ref="captcha"]'
            for i in range(10):
                if sb.is_element_visible(captcha_btn):
                    clean_overlays(sb) # 点击前先清场
                    try:
                        sb.click(captcha_btn) # 普通点击
                        sb.sleep(3)
                        if handle_ad_windows(sb): continue
                        if not sb.is_element_visible(captcha_btn): break
                    except:
                        handle_ad_windows(sb)
                        continue

            # [D] 18秒倒计时巡逻 (维持原样)
            logger.info("⌛ [内存守护] 18秒倒计时，正在清理潜在广告...")
            for _ in range(18):
                sb.sleep(1)
                handle_ad_windows(sb)

            final_btn = 'button#submit-button[data-ref="show"]'
            click_final = False
            for i in range(10):
                if sb.is_element_visible(final_btn):
                    clean_overlays(sb) # 点击前先清场
                    try:
                        sb.click(final_btn) # 普通点击
                        sb.sleep(3)
                        if handle_ad_windows(sb): continue
                        if not sb.is_element_visible(final_btn):
                            click_final = True
                            break
                    except:
                        handle_ad_windows(sb)
                        continue
            
            # --- 阶段 4: 结果数值对比 ---
            logger.info("🏁 [校验] 回访 Pella 验证增量...")
            sb.uc_open_with_reconnect(target_server_url, 10)
            sb.sleep(10)
            text_after = sb.execute_script(js_time_grabber)
            hours_after = parse_time_to_hours(text_after)
            logger.info(f"🕒 [续期后] 原始: {text_after} | 小时: {hours_after}")

            if hours_after > hours_before:
                print("PELLA_SUCCESS_FLAG") 
                send_tg_notification("续期成功 ✅", f"时间增加！\n续期前: {text_before}\n续期后: {text_after}", None)
            else:
                send_tg_notification("保活跳过 🕒", f"检测到时间未增加，维持原计划。当前: {text_after}", None)

        except Exception as e:
            logger.error(f"🔥 [崩溃]: {str(e)}")
            send_tg_notification("保活失败 ❌", f"报错: `{str(e)}`", None)
            raise e

if __name__ == "__main__":
    run_test()
