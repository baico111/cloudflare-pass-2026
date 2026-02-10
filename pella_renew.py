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
# 3. Pella 自动化流程 (物理加固版)
# ==========================================
def run_test():
    email_addr = os.environ.get("EMAIL")
    app_pw = os.environ.get("PASSWORD")
    proxy = os.environ.get("PROXY")
    ui_mode = os.environ.get("BYPASS_MODE", "SB增强模式")
    
    server_id = os.environ.get("SERVER_ID", "c216766d5bbb47fc982167ec08c144b1")
    renew_id = os.environ.get("RENEW_ID", "Q9wFiVeMT6vw")
    target_server_url = f"https://www.pella.app/server/{server_id}"
    renew_url = f"https://cuttlinks.com/{renew_id}"
    
    # 物理加固 1: 启动参数优化，增加页面加载策略
    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None, page_load_strategy="normal") as sb:
        try:
            # --- 第一阶段: 登录 (解决 ERR_EMPTY_RESPONSE 问题) ---
            logger.info("📡 尝试建立初始连接...")
            # 物理加固 2: 强制使用这种方式打开，如果报错则自动重试 3 次
            for _ in range(3):
                try:
                    sb.activate_cdp() # 激活底层协议，增强穿透
                    sb.uc_open_with_reconnect("https://www.pella.app/login", 15)
                    if "pella.app" in sb.get_current_url(): break
                except:
                    sb.sleep(5)
                    sb.driver.refresh()
            
            sb.sleep(5)
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
                    send_tg_notification("冷却中 🕒", f"按钮尚在冷却。剩余: {expiry_before}", None)
                    return 

            # --- 第三阶段: 跳转续期 (解决卡死/黑屏问题) ---
            logger.info(f"🚀 跳转至续期网站: {renew_url}")
            
            # 物理加固 3: 跳转前彻底清理所有挂起的 JS 任务
            sb.execute_script("window.stop();")
            time.sleep(2)
            
            # 物理加固 4: 强制在新页面打开以打破之前的 Session 阻塞
            sb.execute_script(f"window.open('{renew_url}', '_blank');")
            sb.sleep(5)
            sb.switch_to_window(1) # 切换到新打开的续期页
            
            # 如果没打开，就地重试
            if "cuttlinks.com" not in sb.get_current_url():
                sb.uc_open_with_reconnect(renew_url, 20)

            for i in range(5):
                if sb.is_element_visible('button#submit-button[data-ref="first"]'):
                    sb.js_click('button#submit-button[data-ref="first"]')
                    sb.sleep(3)
                    # 自动清理弹出的劫持广告窗口
                    if len(sb.driver.window_handles) > 2:
                        for handle in sb.driver.window_handles[2:]:
                            sb.driver.switch_to.window(handle)
                            sb.driver.close()
                        sb.driver.switch_to.window(sb.driver.window_handles[1])
                    if not sb.is_element_visible('button#submit-button[data-ref="first"]'): break

            # --- 算法分支 ---
            sb.sleep(6)
            try:
                from simple_bypass import bypass_cloudflare as api_core_2
                from simple_bypass import bypass_parallel as api_core_3
                from bypass_seleniumbase import bypass_logic as api_core_4
                
                current_url = sb.get_current_url()
                if "单浏览器" in ui_mode: api_core_2(current_url, proxy=proxy)
                elif "并行竞争" in ui_mode: api_core_3(url=current_url, proxy_file="proxy.txt", batch_size=3)
                elif "SB增强" in ui_mode: api_core_4(sb)
            except: pass

            captcha_btn = 'button#submit-button[data-ref="captcha"]'
            for i in range(6):
                if sb.is_element_visible(captcha_btn):
                    sb.js_click(captcha_btn)
                    sb.sleep(3)
                    if len(sb.driver.window_handles) > 2:
                        curr = sb.driver.current_window_handle
                        for h in sb.driver.window_handles:
                            if h != curr and h != sb.driver.window_handles[0]: 
                                sb.driver.switch_to.window(h); sb.driver.close()
                        sb.driver.switch_to.window(curr)
                    if not sb.is_element_visible(captcha_btn): break

            logger.info("等待计时结束...")
            sb.sleep(18)
            final_btn = 'button#submit-button[data-ref="show"]'
            for i in range(8):
                if sb.is_element_visible(final_btn):
                    sb.js_click(final_btn)
                    sb.sleep(3)
                    if not sb.is_element_visible(final_btn): break

            # --- 第四阶段: 结果验证 ---
            logger.info("操作完成，回访 Pella...")
            sb.switch_to_window(0) # 切回 Pella 页面
            sb.uc_open_with_reconnect(target_server_url, 15)
            sb.sleep(10)
            expiry_after = get_expiry_time_raw(sb)
            sb.save_screenshot("/app/output/pella_final_result.png")
            send_tg_notification("续期成功 ✅", f"续期前: {expiry_before}\n续期后: {expiry_after}", "/app/output/pella_final_result.png")

        except Exception as e:
            sb.save_screenshot("/app/output/error.png")
            send_tg_notification("流程异常 ❌", f"错误详情: `{str(e)}`", "/app/output/error.png")
            raise e

if __name__ == "__main__":
    run_test()
