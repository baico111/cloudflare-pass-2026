import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from seleniumbase import SB
from loguru import logger

# ==========================================
# 1. 严格按照仓库 API 逻辑进行函数导入 (完全不改)
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
# 2. 高科技 TGUI 功能 (北京时间锁死)
# ==========================================
def send_tg_notification(status, message, photo_path=None):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat_id): return
    
    # 强制锁死北京时间 (UTC+8)
    tz_bj = timezone(timedelta(hours=8))
    bj_time = datetime.now(tz_bj).strftime('%Y-%m-%d %H:%M:%S')
    emoji = "✅" if "成功" in status else "⚠️" if "未到期" in status else "❌"
    
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
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", 
                              data={'chat_id': chat_id, 'caption': formatted_msg, 'parse_mode': 'Markdown'}, files={'photo': f})
        else:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                          data={'chat_id': chat_id, 'text': formatted_msg, 'parse_mode': 'Markdown'})
    except Exception as e: logger.error(f"TG通知失败: {e}")

# ==========================================
# 3. 自动化续期主流程
# ==========================================
def run_auto_renew():
    email = os.environ.get("EMAIL")
    password = os.environ.get("PASSWORD")
    ui_mode = os.environ.get("BYPASS_MODE", "1. 基础单次模式")
    
    # --- 核心修改：从环境变量读取动态 ID (默认为 177688) ---
    server_id = os.environ.get("SERVER_ID", "177688")
    # --- 核心修改：读取代理变量 ---
    proxy = os.environ.get("PROXY")
    
    login_url = "https://dashboard.katabump.com/auth/login"
    # 动态拼接目标页面 URL
    target_url = f"https://dashboard.katabump.com/servers/edit?id={server_id}"
    
    OUTPUT_DIR = Path("/app/output")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

   with SB(uc= True , xvfb= True , proxy=proxy if proxy else  None ) as sb:
        尝试：
            # ---- [步骤 A] 填表登录 ----
            logger.info( f"🚀 访问登录页: {login_url} " )
            sb.uc_open_with_reconnect(login_url, 10 )
            sb.wait_for_element_visible( "#email" , timeout= 25 )
            sb.execute_script( f'document.querySelector("#email").value = " {email} "' )
            sb.execute_script( f'document.querySelector("#password").value = " {password} "' )
            sb.type ( "#email" , email)
            sb.type ( "#password" , password)
            
            # 登录页破盾
            current_url = sb.get_current_url()
            logger.info( f"🛡️ 登录页启动模式: {ui_mode}破解算法..." )
            如果ui_mode 中为“1.” ：api_core_1(current_url)
            elif  "2."  in ui_mode: api_core_2(current_url, proxy=os.environ.get( "PROXY" ))
            elif  "3."  in ui_mode: api_core_3(url=current_url, proxy_file= "proxy.txt" , batch_size= 3 )
            elif  "4."  in ui_mode: api_core_4(sb)

            尝试：sb.uc_gui_click_captcha()
            例外：通过
            
            logger.info( "🖱️点击提交登录按钮..." )
            sb.click( "#submit" )
            sb.sleep( 15 )

            # ---- [步骤 B] 跳转至 Renew 页面 ----
            logger.info(f"📡 正在跳转至服务器管理页 (ID: {server_id})...")
            sb.uc_open_with_reconnect(target_url, 10)
            sb.sleep(3)
            
            logger.info("📦 正在激活 Renew 模态框...")
            sb.js_click('button[data-bs-target="#renew-modal"]') 
            sb.sleep(6)

            # ---- [步骤 C] 调用核心 API ----
            current_url = sb.get_current_url()
            logger.info(f"🛡️ 当前模式: {ui_mode}，正在启动破解算法...")
            if "1." in ui_mode: result = api_core_1(current_url)
            elif "2." in ui_mode: result = api_core_2(current_url, proxy=os.environ.get("PROXY"))
            elif "3." in ui_mode: result = api_core_3(url=current_url, proxy_file="proxy.txt", batch_size=3)
            elif "4." in ui_mode: 
                api_core_4(sb)
                result = {"success": True}

            # ---- [步骤 D] 整合成果与精准点击 ----
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

            # ---- [步骤 E] 结果抓取 (深度防乱码逻辑) ----
            logger.info("🔄 正在刷新页面以获取最新到期日期...")
            sb.refresh()
            
            logger.info("🔍 正在定位到期日期元素...")
            # 增加等待，确保日期元素渲染完成
            sb.wait_for_element_visible('//div[contains(text(), "Expiry")]', timeout=15)
            sb.sleep(5) 
            
            final_img = str(OUTPUT_DIR / "final_result.png")
            sb.save_screenshot(final_img)
            
            page_source = sb.get_page_source()
            
            # 精准日期提取逻辑
            if "2026-" in page_source:
                logger.info("✅ 检测到日期刷新，正在提取...")
                try:
                    # 锚点定位：Expiry 文本后的第一个 div 兄弟
                    expiry_date = sb.get_text('//div[contains(text(), "Expiry")]/following-sibling::div')
                    # 强制截断，只取 10 位，彻底杀灭 katassv
                    clean_date = expiry_date.strip()[:10]
                    
                    if not clean_date.startswith("20"):
                        raise Exception("抓取格式不符")

                    send_tg_notification("续期成功 ✅", f"服务器续期已生效！\n📅 **下次到期**: `{clean_date}`", final_img)
                except:
                    # 备选 CSS 定位 (针对可能出现的表格结构)
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
