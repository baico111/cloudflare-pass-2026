import os
import time
import imaplib
import email
import re
import requests
import sys
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from seleniumbase import SB
from loguru import logger
from huggingface_hub import upload_file

# ==========================================
# 1. TG 通知功能 (锁死对齐 CF 中转)
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    cf_proxy_url = os.environ.get("TG_PROXY_URL") 
    cf_auth_key = os.environ.get("TG_AUTH_KEY")   
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if cf_proxy_url and cf_auth_key:
        target_base = f"{cf_proxy_url}/{token}"
        headers = {"X-Custom-Auth": cf_auth_key}
    else:
        target_base = f"https://api.telegram.org/bot{token}"
        headers = {}

    if not (token and chat_id): return
    tz_bj = timezone(timedelta(hours=8))
    bj_time = datetime.now(tz_bj).strftime('%Y-%m-%d %H:%M:%S')
    emoji = "✅" if "成功" in status else "❌"
    formatted_msg = f"{emoji} **Pella 自动化续期报告**\n━━━━━━━━━━━━━━━━━━\n👤 **账户**: `{os.environ.get('PELLA_EMAIL')}`\n📡 **状态**: {status}\n📝 : {message}\n🕒 **北京时间**: `{bj_time}`\n━━━━━━━━━━━━━━━━━━"
    try:
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                requests.post(f"{target_base}/sendPhoto", data={'chat_id': chat_id, 'caption': formatted_msg, 'parse_mode': 'Markdown'}, headers=headers, files={'photo': f}, timeout=30)
        else:
            requests.post(f"{target_base}/sendMessage", data={'chat_id': chat_id, 'text': formatted_msg, 'parse_mode': 'Markdown'}, headers=headers, timeout=30)
    except Exception as e: logger.error(f"TG通知失败: {e}")

# --- HF 同步工具 ---
HF_DATASET_ID = os.environ.get("HF_DATASET_ID")
HF_TOKEN = os.environ.get("HF_TOKEN")
def sync_image_to_cloud(file_path):
    if HF_TOKEN and HF_DATASET_ID and os.path.exists(file_path):
        try: upload_file(path_or_fileobj=file_path, path_in_repo=os.path.basename(file_path), repo_id=HF_DATASET_ID, repo_type="dataset", token=HF_TOKEN)
        except: pass

# ==========================================
# 2. 验证码提取 (✨ 核心修复：物理切换为基站爬虫模式)
# ==========================================
def get_pella_code(mail_address, kuma_url):
    # 💡 物理原理：这里的 kuma_url 即面板中 Password 框填写的状态页地址
    if not kuma_url or "http" not in kuma_url:
        logger.error(f"❌ [物理报错] Kuma URL 无效: {kuma_url}")
        return None

    logger.info(f"📡 [物理穿透] 正在访问基站检索验证码: {kuma_url}")
    
    # 物理尝试自动识别推送 ID 用于阅后即焚（可选）
    push_id_match = re.search(r'paycifwva[a-z0-9]+', kuma_url)
    reset_url = f"http://168.110.213.248:12121/api/push/{push_id_match.group()}?status=up&msg=OK" if push_id_match else None

    try:
        for i in range(20): # 增加轮询时长
            r = requests.get(kuma_url, timeout=10)
            if r.status_code == 200:
                # 在 HTML 源码中直接寻找 6 位数字验证码
                code = re.search(r'\b\d{6}\b', r.text)
                if code:
                    auth_code = code.group()
                    logger.success(f"🎯 [物理命中] 验证码抓取成功: {auth_code}")
                    # 阅后即焚
                    if reset_url:
                        try: requests.get(reset_url, timeout=5)
                        except: pass
                    return auth_code
            
            logger.info(f"⌛ 第 {i+1} 轮轮询中，等待基站数据刷新...")
            time.sleep(10)
        return None
    except Exception as e: 
        logger.error(f"🔥 基站物理访问故障: {e}")
        return None

# ==========================================
# 3. 辅助功能 (100% 还原)
# ==========================================
def parse_time_to_hours(text):
    if not text or "未找到" in text: return 0
    try:
        total_hours = 0
        days = re.search(r'(\d+)\s*Day', text, re.I); hours = re.search(r'(\d+)\s*(?:Hour|h|Minute|M)', text, re.I)
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
                sb_obj.driver.switch_to.window(h); sb_obj.driver.close()
            sb_obj.driver.switch_to.window(main_h); return True
    except: pass
    return False

def clean_overlays(sb_obj):
    try:
        js = "var divs = document.querySelectorAll('div'); for (var i = 0; i < divs.length; i++) { var style = window.getComputedStyle(divs[i]); if (parseInt(style.zIndex) > 1000 || style.position === 'fixed') { divs[i].remove(); } }"
        sb_obj.execute_script(js); logger.info("🧹 [清场] 已清理隐形拦截层")
    except: pass

# ==========================================
# 4. Pella 自动化主流程 (🔥 全量逻辑复刻，一个字不改)
# ==========================================
def run_test():
    email_addr = os.environ.get("PELLA_EMAIL"); app_pw = os.environ.get("GMAIL_APP_PASSWORD")
    server_id = os.environ.get("SERVER_ID", "2b3bbeef0eeb452299a11e431c3c2d5b")
    renew_id = os.environ.get("RENEW_ID", "m4w0wJrEmgEC"); proxy = os.environ.get("PROXY")
    target_server_url = f"https://www.pella.app/server/{server_id}"; renew_url = f"https://cuty.io/{renew_id}"
    
    # 物理隔离存储
    account_prefix = email_addr.split('@')[0] if email_addr else "default"
    OUTPUT_ROOT = Path(f"/app/output/pella_renew/{account_prefix}")
    if OUTPUT_ROOT.exists(): shutil.rmtree(OUTPUT_ROOT)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    output_img = "final_result.png"; error_img = "error.png"

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

    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None, chromium_arg="--blink-settings=imagesEnabled=false") as sb:
        try:
            # --- 阶段 1: 登录与验证码 ---
            logger.info("🚀 [阶段1] 进入 Pella...")
            sb.uc_open_with_reconnect("https://www.pella.app/login", 10)
            sb.sleep(5); sb.uc_gui_click_captcha()
            sb.wait_for_element_visible("#identifier-field", timeout=25)
            for char in email_addr: sb.add_text("#identifier-field", char); time.sleep(0.1)
            sb.press_keys("#identifier-field", "\n")
            
            sb.sleep(5)
            auth_code = get_pella_code(email_addr, app_pw)
            if not auth_code: raise Exception("验证码抓取失败")
            sb.type('input[data-input-otp="true"]', auth_code); sb.sleep(10)

            # --- 阶段 2: 审计前时间 ---
            sb.uc_open_with_reconnect(target_server_url, 10); sb.sleep(10)
            text_before = sb.execute_script(js_time_grabber)
            hours_before = parse_time_to_hours(text_before)

            # --- 阶段 3: 🔥 续期执行 ---
            logger.info(f"🚀 [阶段3] 跳转续期外部链接: {renew_url}")
            sb.uc_open_with_reconnect(renew_url, 10); sb.sleep(5); handle_ad_windows(sb)
            
            # [A] 第一个 Continue
            for i in range(10):
                if sb.is_element_visible('button#submit-button[data-ref="first"]'):
                    clean_overlays(sb)
                    try:
                        sb.click('button#submit-button[data-ref="first"]')
                        logger.info(f"🖱️ [自证] 第 {i+1} 次尝试点击第一个 Continue...")
                        sb.sleep(3)
                        if handle_ad_windows(sb): continue
                        if not sb.is_element_visible('button#submit-button[data-ref="first"]'): break
                    except: handle_ad_windows(sb); continue

            # [B] Cloudflare 穿透
            sb.sleep(5); handle_ad_windows(sb)
            try:
                cf_iframe = 'iframe[src*="cloudflare"]'
                if sb.is_element_visible(cf_iframe):
                    logger.info("🛡️ [自证] 检测到 Cloudflare 阻挡，正在穿透...")
                    sb.switch_to_frame(cf_iframe); sb.click('span.mark'); sb.switch_to_parent_frame(); sb.sleep(6)
            except: pass

            # [C] I am not a robot
            captcha_btn = 'button#submit-button[data-ref="captcha"]'
            for i in range(10):
                if sb.is_element_visible(captcha_btn):
                    clean_overlays(sb); 
                    try:
                        sb.click(captcha_btn); logger.info(f"🖱️ [自证] 第 {i+1} 次点击 I am not a robot...")
                        sb.sleep(3)
                        if handle_ad_windows(sb): continue
                        if not sb.is_element_visible(captcha_btn): break
                    except: handle_ad_windows(sb); continue

            # [D] 18秒倒计时巡逻
            logger.info("⌛ [自证] 进入 18 秒强制巡逻期...")
            for s in range(18): sb.sleep(1); handle_ad_windows(sb)

            # [E] 最终 Go 按钮
            final_btn = 'button#submit-button[data-ref="show"]'
            for i in range(10):
                if sb.is_element_visible(final_btn):
                    clean_overlays(sb); 
                    try:
                        sb.click(final_btn); logger.info(f"🖱️ [自证] 第 {i+1} 次点击最终 Go 按钮...")
                        sb.sleep(3)
                        if handle_ad_windows(sb): continue
                        if not sb.is_element_visible(final_btn): break
                    except: handle_ad_windows(sb); continue

            # --- 阶段 4: 结果审计 ---
            sb.uc_open_with_reconnect(target_server_url, 10); sb.sleep(10)
            text_after = sb.execute_script(js_time_grabber)
            hours_after = parse_time_to_hours(text_after)
            
            sb.save_screenshot(output_img); shutil.copy(output_img, str(OUTPUT_ROOT / output_img))
            sync_image_to_cloud(output_img)
            
            if hours_after > hours_before:
                send_tg_notification("续期成功 ✅", f"续期成功！\n前: {text_before}\n后: {text_after}", output_img)
            else:
                send_tg_notification("保活跳过 🕒", f"当前时间: {text_after}", output_img)

        except Exception as e:
            sb.save_screenshot(error_img); shutil.copy(error_img, str(OUTPUT_ROOT / error_img))
            sync_image_to_cloud(error_img)
            send_tg_notification("保活失败 ❌", f"报错: `{str(e)}`", error_img)
            raise e

if __name__ == "__main__":
    run_test()
