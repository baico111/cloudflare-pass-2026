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
# 3. Pella 自动化流程 (主逻辑完全不动)
# ==========================================
def run_test():
    # 改动点：对齐面板环境变量名
    email_addr = os.environ.get("EMAIL")
    app_pw = os.environ.get("PASSWORD")
    proxy = os.environ.get("PROXY")
    ui_mode = os.environ.get("BYPASS_MODE", "SB增强模式")
    
    server_id = os.environ.get("SERVER_ID", "c216766d5bbb47fc982167ec08c144b1")
    renew_id = os.environ.get("RENEW_ID", "Q9wFiVeMT6vw")
    target_server_url = f"https://www.pella.app/server/{server_id}"
    renew_url = f"https://cuttlinks.com/{renew_id}"
    
    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None) as sb:
        try:
            # --- 第一阶段: 登录 ---
            logger.info("🚀 [面板监控] 正在打开 Pella 登录页面...")
            sb.uc_open_with_reconnect("https://www.pella.app/login", 20)
            sb.sleep(5)
            sb.uc_gui_click_captcha()
            sb.wait_for_element_visible("#identifier-field", timeout=60)
            
            logger.info(f"⌨️ [面板监控] 正在输入账号: {email_addr}")
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

            # --- 第二阶段: 检查状态 ---
            logger.info("🔍 [面板监控] 正在回访服务器页面检查初始时长...")
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
            logger.info(f"🕒 [面板监控] 续期前时长: {expiry_before}")

            target_btn = 'a[href*="tpi.li/FSfV"]'
            if sb.is_element_visible(target_btn):
                if "opacity-50" in sb.get_attribute(target_btn, "class"):
                    logger.warning("🕒 [面板监控] 按钮处于冷却状态，跳过后续操作。")
                    send_tg_notification("冷却中 🕒", f"按钮尚在冷却。剩余: {expiry_before}", None)
                    return 

            # --- 第三阶段: 续期网站操作 (物理日志监控) ---
            logger.info(f"🚀 [面板监控] 正在物理跳转至续期站: {renew_url}")
            sb.execute_script("window.stop();") # 物理加固：停止背景加载
            sb.uc_open_with_reconnect(renew_url, 20)
            sb.sleep(8)
            
            # 记录主窗口句柄
            main_window = sb.driver.current_window_handle
            logger.info(f"🌐 [面板监控] 续期页已打开，当前 URL: {sb.get_current_url()}")

            for i in range(5):
                logger.info(f"🖱️ [面板监控] 尝试点击 [First] 按钮 (第 {i+1}/5 次)...")
                if sb.is_element_visible('button#submit-button[data-ref="first"]'):
                    sb.js_click('button#submit-button[data-ref="first"]')
                    sb.sleep(3)
                    
                    # 物理修正：点击即弹窗时，直接物理关闭广告标签页
                    if len(sb.driver.window_handles) > 1:
                        logger.info(f"⚠️ [面板监控] 检测到弹窗广告 (数量: {len(sb.driver.window_handles)-1})，正在物理关闭...")
                        for handle in sb.driver.window_handles:
                            if handle != main_window:
                                sb.driver.switch_to.window(handle)
                                sb.driver.close()
                        sb.driver.switch_to.window(main_window)
                    
                    if not sb.is_element_visible('button#submit-button[data-ref="first"]'):
                        logger.info("✅ [面板监控] [First] 按钮点击成功，已消失。")
                        break
                else:
                    logger.warning(f"⏳ [面板监控] 没看到按钮，当前 URL: {sb.get_current_url()}")
                    sb.sleep(3)

            # --- 算法分支 (人机验证前置) ---
            logger.info(f"🛡️ [面板监控] 正在按面板选择模式执行破解: {ui_mode}")
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
                logger.info("✅ [面板监控] 破解算法环节已通过。")
            except Exception as e:
                logger.error(f"❌ [面板监控] 算法执行报错: {e}")

            # 再次清理由于算法可能产生的多余窗口
            if len(sb.driver.window_handles) > 1:
                for h in sb.driver.window_handles:
                    if h != main_window: sb.driver.switch_to.window(h); sb.driver.close()
                sb.driver.switch_to.window(main_window)

            # 流程后续点击 (逻辑一字未动)
            for btn_ref in ["captcha", "show"]:
                selector = f'button#submit-button[data-ref="{btn_ref}"]'
                logger.info(f"🔍 [面板监控] 寻找 [{btn_ref}] 按钮...")
                for i in range(8):
                    if sb.is_element_visible(selector):
                        logger.info(f"🖱️ [面板监控] 点击 [{btn_ref}] 按钮")
                        sb.js_click(selector)
                        sb.sleep(3)
                        if len(sb.driver.window_handles) > 1:
                            for h in sb.driver.window_handles:
                                if h != main_window: sb.driver.switch_to.window(h); sb.driver.close()
                            sb.driver.switch_to.window(main_window)
                        if not sb.is_element_visible(selector): break
                if btn_ref == "captcha":
                    logger.info("⌛ [面板监控] 进入 18 秒等待计时...")
                    sb.sleep(18)

            # --- 第四阶段: 返回 Pella 验证结果 ---
            logger.info("🏁 [面板监控] 流程全部结束，正在回访 Pella 验证最终时长...")
            sb.sleep(5)
            sb.uc_open_with_reconnect(target_server_url, 15)
            sb.sleep(10)
            
            expiry_after = get_expiry_time_raw(sb)
            logger.info(f"🕒 [面板监控] 续期后时长: {expiry_after}")
            sb.save_screenshot("pella_final_result.png")
            
            send_tg_notification("续期成功 ✅", f"续期前: {expiry_before}\n续期后: {expiry_after}", "pella_final_result.png")

        except Exception as e:
            logger.error(f"🔥 [面板监控] 流程崩溃: {str(e)}")
            sb.save_screenshot("error.png")
            send_tg_notification("流程异常 ❌", f"错误详情: `{str(e)}`", "error.png")
            raise e

if __name__ == "__main__":
    run_test()
