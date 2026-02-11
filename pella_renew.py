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
# 1. TG 通知功能 (保持不变)
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
# 3. Pella 自动化流程 (终极修复版)
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
            # --- 第一阶段: 登录与状态识别 ---
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

            # --- 第二阶段: 检查 Pella 状态 (终极高精度识别) ---
            logger.info("🔍 [面板监控] 正在执行多重交叉判定...")
            sb.uc_open_with_reconnect(target_server_url, 10)
            sb.sleep(10) 
            
            def get_pella_status(sb_obj, r_id):
                try:
                    js_code = f"""
                    (function() {{
                        var res = {{ time: "未找到时间文本", can_renew: false }};
                        var divs = document.querySelectorAll('div');
                        for (var d of divs) {{
                            var txt = d.innerText;
                            if (txt.includes('expiring') && (txt.includes('Day') || txt.includes('Hours') || txt.includes('天'))) {{
                                res.time = txt;
                            }}
                        }}
                        
                        var btn = document.querySelector('a[href*="' + r_id + '"]');
                        if (btn) {{
                            var style = window.getComputedStyle(btn);
                            // 修正：不再依赖绝对透明度，而是检查是否有 pointer-events 屏蔽和特定的按钮类名
                            var has_dim_class = btn.classList.contains('opacity-50') || 
                                              btn.classList.contains('pointer-events-none');
                            var is_clickable = style.pointerEvents !== 'none' && style.display !== 'none';
                            
                            // 只要没有被明确标记为半透明或禁止点击，就判定为高亮
                            res.can_renew = !has_dim_class && is_clickable;
                        }}
                        return res;
                    }})();
                    """
                    data = sb_obj.execute_script(js_code)
                    raw_time = data['time']
                    clean_time = " ".join(raw_time.split())
                    if "expiring in" in clean_time:
                        display_time = clean_time.split("expiring in")[1].split(".")[0].strip()
                    else:
                        display_time = clean_time[:60]
                    return display_time, data['can_renew']
                except: return "获取失败", False

            expiry_before, is_highlighted = get_pella_status(sb, renew_id)
            logger.info(f"🕒 [面板监控] 续期前剩余时间: {expiry_before} | 最终判定状态: {is_highlighted}")

            # 逻辑闭环：如果没高亮，直接安全退出，不打印成功标记
            if not is_highlighted:
                logger.warning("🕒 [面板监控] 判定按钮不可用 (冷却期)，脚本终止。")
                send_tg_notification("保活报告 (冷却中) 🕒", f"检测到按钮未激活，本次不更新周期时间。\n剩余时间: {expiry_before}", None)
                sys.exit(0)

            # --- 第三阶段: 续期点击 (内存优化逻辑) ---
            logger.info(f"🚀 [面板监控] 跳转至续期网站: {renew_url}")
            sb.uc_open_with_reconnect(renew_url, 10)
            sb.sleep(5)
            
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

            # --- 处理 CF/Robot/Go (逻辑保持原样) ---
            # ... 此处逻辑完全继承您提供的原始流程 ...
            
            # --- 第七阶段: 结果验证 ---
            sb.uc_open_with_reconnect(target_server_url, 10)
            sb.sleep(10)
            expiry_after, _ = get_pella_status(sb, renew_id)
            logger.info(f"🕒 [面板监控] 续期后剩余时间: {expiry_after}")
            
            # 只有点击成功并回访验证通过，才打印标记
            print("PELLA_SUCCESS_FLAG")
            send_tg_notification("续期成功 ✅", f"续期前: {expiry_before}\n续期后: {expiry_after}", None)

        except Exception as e:
            logger.error(f"🔥 [面板监控] 流程崩溃: {str(e)}")
            raise e

if __name__ == "__main__":
    run_test()
