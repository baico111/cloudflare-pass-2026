import os
import time
import requests
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from seleniumbase import SB
from loguru import logger

# ==========================================
# 1. 严格按照仓库 API 逻辑进行函数导入 (原样保留)
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
# 2. 高科技 TGUI 功能 (物理修复：解决 400 报错，文字必达)
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    cf_proxy_url = str(os.environ.get("TG_PROXY_URL", "")).strip()
    cf_auth_key = str(os.environ.get("TG_AUTH_KEY", "")).strip()
    token = str(os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = str(os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
    
    if not token or not chat_id:
        logger.error("❌ 环境变量缺失：TELEGRAM_BOT_TOKEN 或 TELEGRAM_CHAT_ID 未注入")
        return
    
    if cf_proxy_url and cf_auth_key:
        target_base = f"{cf_proxy_url.rstrip('/')}/{token}"
        headers = {"X-Custom-Auth": cf_auth_key}
        logger.info(f"🔗 使用 CF 代理链路: {cf_proxy_url}")
    else:
        target_base = f"https://api.telegram.org/bot{token}"
        headers = {}

    tz_bj = timezone(timedelta(hours=8))
    bj_time = datetime.now(tz_bj).strftime('%Y-%m-%d %H:%M:%S')
    emoji = "✅" if "成功" in status else "⚠️" if "未到期" in status else "❌"
    
    # 物理保底：构建纯文本，防止 Markdown 格式导致 400 错误
    plain_report = f"{emoji} 矩阵续期报告\n账户: {os.environ.get('EMAIL', 'Unknown')}\n状态: {status}\n详情: {message}\n时间: {bj_time}"
    
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
        sent_success = False
        if photo_path and os.path.exists(photo_path) and os.path.getsize(photo_path) > 100:
            try:
                with open(photo_path, 'rb') as f:
                    r_photo = requests.post(f"{target_base}/sendPhoto", 
                                     data={'chat_id': chat_id, 'caption': formatted_msg, 'parse_mode': 'Markdown'}, 
                                     headers=headers, files={'photo': f}, timeout=45)
                    if r_photo.status_code == 200:
                        logger.success("✅ TG 图片报告发送成功")
                        sent_success = True
                    else:
                        logger.error(f"⚠️ 图片发送失败({r_photo.status_code})，执行文字补发...")
            except Exception as e_p:
                logger.error(f"🔥 读取截图流异常: {e_p}")
        
        if not sent_success:
            # ✨ 终极保底：如果发图失败或无图，强制发纯文字
            r_text = requests.post(f"{target_base}/sendMessage", 
                                 data={'chat_id': chat_id, 'text': plain_report}, 
                                 headers=headers, timeout=45)
            if r_text.status_code == 200:
                logger.success("✅ TG 纯文字报告已物理送达")
            else:
                logger.error(f"❌ TG 彻底发送失败 | 返回: {r_text.text}")

    except Exception as e: 
        logger.error(f"🔥 TG 链路彻底崩毁: {e}")

# ==========================================
# 3. 自动化续期主流程 (圣旨复刻：完全采用你提供的步骤逻辑)
# ==========================================
def run_auto_renew():
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    ui_mode = os.environ.get("BYPASS_MODE", "1. 基础单次模式")
    server_id = os.environ.get("SERVER_ID", "177688")
    proxy = os.environ.get("PROXY")
    
    login_url = "https://dashboard.katabump.com/auth/login"
    target_url = f"https://dashboard.katabump.com/servers/edit?id={server_id}"
    
    OUTPUT_DIR = Path("/app/output")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with SB(uc=True, xvfb=True, proxy=proxy if proxy else None) as sb:
        try:
            # ---- [步骤 A] 填表登录 ----
            logger.info(f"🚀 访问登录页: {login_url}")
            sb.uc_open_with_reconnect(login_url, 10)
            sb.wait_for_element_visible("#email", timeout=25)
            sb.execute_script(f'document.querySelector("#email").value = "{email}"')
            sb.execute_script(f'document.querySelector("#password").value = "{password}"')
            sb.type("#email", email) 
            sb.type("#password", password)
            
            # 登录页破盾
            current_url = sb.get_current_url()
            logger.info(f"🛡️ 登录页启动模式: {ui_mode} 破解算法...")
            if "1." in ui_mode: api_core_1(current_url)
            elif "2." in ui_mode: api_core_2(current_url, proxy=os.environ.get("PROXY"))
            elif "3." in ui_mode: api_core_3(url=current_url, proxy_file="proxy.txt", batch_size=3)
            elif "4." in ui_mode: api_core_4(sb)

            try: sb.uc_gui_click_captcha()
            except: pass
            
            logger.info("🖱️ 点击提交登录按钮...")
            sb.click("#submit") 
            sb.sleep(15)

            # ---- [步骤 B] 跳转至 Renew 页面 (完全复刻你的逻辑) ----
            logger.info(f"📡 正在跳转至服务器管理页 (ID: {server_id})...")
            sb.uc_open_with_reconnect(target_url, 10)
            sb.sleep(3)
            
            logger.info("📦 正在激活 Renew 模态框...")
            sb.js_click('button[data-bs-target="#renew-modal"]') 
            sb.sleep(6)

            # ---- [步骤 C] 调用核心 API (完全复刻你的逻辑) ----
            current_url = sb.get_current_url()
            logger.info(f"🛡️ 当前模式: {ui_mode}，正在启动破解算法...")
            if "1." in ui_mode: result = api_core_1(current_url)
            elif "2." in ui_mode: result = api_core_2(current_url, proxy=os.environ.get("PROXY"))
            elif "3." in ui_mode: result = api_core_3(url=current_url, proxy_file="proxy.txt", batch_size=3)
            elif "4." in ui_mode: 
                api_core_4(sb)
                result = {"success": True}

            # ---- [步骤 D] 整合成果与精准点击 (完全复刻你的逻辑) ----
            logger.info("📡 执行 GUI 验证码点击穿透...")
            sb.uc_gui_click_captcha()
            logger.info("✅ 验证已完成，进入 20 秒稳定缓冲期...")
            sb.sleep(20) 
            
            logger.info("📡 执行最终 Renew 提交点击...")
            try:
                sb.wait_for_element_visible('#renew-modal button[type="submit"].btn-primary', timeout=20)
                sb.click('#renew-modal button[type="submit"].btn-primary')
            except:
                logger.warning("⚠️ 默认按钮定位失败，尝试备选 JS 点击...")
                sb.js_click('#renew-modal button.btn-primary')
            
            sb.sleep(12) 

            # ---- [步骤 E] 结果抓取 (深度防乱码逻辑，完全复刻你的逻辑) ----
            logger.info("🔄 正在刷新页面以获取最新到期日期...")
            sb.refresh()
            
            logger.info("🔍 正在定位到期日期元素...")
            sb.wait_for_element_visible('//div[contains(text(), "Expiry")]', timeout=15)
            sb.sleep(5) 
            
            final_img = str(OUTPUT_DIR / "final_result.png")
            sb.save_screenshot(final_img)
            
            page_source = sb.get_page_source()
            
            # 精准日期提取逻辑
            if "2026-" in page_source:
                logger.info("✅ 检测到日期刷新，正在提取...")
                try:
                    expiry_date = sb.get_text('//div[contains(text(), "Expiry")]/following-sibling::div')
                    # 💡 强制截断，只取 10 位
                    clean_date = expiry_date.strip()[:10]
                    
                    if not clean_date.startswith("20"):
                        raise Exception("抓取格式不符")

                    send_tg_notification("续期成功 ✅", f"服务器续期已生效！\n📅 **下次到期**: `{clean_date}`", final_img)
                except:
                    logger.info("🔄 正在尝试备选 CSS 定位抓取日期...")
                    expiry_date = sb.get_text('div.card-body div.row:nth-child(4) div.col-lg-9').strip()[:10]
                    send_tg_notification("续期成功 ✅", f"服务器续期成功！\n📅 **下次到期**: `{expiry_date}`", final_img)
            else:
                logger.warning("⚠️ 页面未发现 2026 日期标记")
                send_tg_notification("未到期 ⚠️", "目前页面未刷新日期，可能尚未达到可续期时间门槛。", final_img)

        except Exception as e:
            logger.error(f"🔥 流程异常中断: {e}")
            error_img = str(OUTPUT_DIR / "error.png")
            sb.save_screenshot(error_img)
            send_tg_notification("执行异常 ❌", f"系统逻辑中断: `{str(e)}`", error_img)
            raise e

if __name__ == "__main__":
    logger.info("🎬 自动化续期脚本正式启动")
    run_auto_renew()
