# ============================================================
# SeleniumBase UC Mode 实现
# 基于 SeleniumBase 的 Undetected ChromeDriver 模式
# 用于绕过 Cloudflare Turnstile 验证
# ============================================================

import time
import random
import json
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable
from datetime import datetime
from loguru import logger

from seleniumbase import SB, Driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import (
    BrowserConfig,
    TurnstileConfig,
    CaptureConfig,
    DEFAULT_BROWSER_CONFIG,
    DEFAULT_TURNSTILE_CONFIG,
    DEFAULT_CAPTURE_CONFIG,
    SCREENSHOTS_DIR,
    USER_AGENTS
)
from utils.request_capture import RequestCaptureManager
from utils.mouse_trajectory import generate_human_like_trajectory, simulate_click_duration


class CloudflareBypassSeleniumBase:
    """
    基于 SeleniumBase UC Mode 的 Cloudflare 绕过工具
    
    主要功能:
    1. 自动检测并绕过 Cloudflare Turnstile 验证
    2. 捕获所有网络请求和响应
    3. 保存 Cookie 和认证信息
    4. 支持拟人化鼠标轨迹
    """
    
    def __init__(
        self,
        browser_config: Optional[BrowserConfig] = None,
        turnstile_config: Optional[TurnstileConfig] = None,
        capture_config: Optional[CaptureConfig] = None,
        session_name: str = "seleniumbase_session"
    ):
        """
        初始化绕过工具
        
        参数:
            browser_config: 浏览器配置
            turnstile_config: Turnstile验证配置
            capture_config: 请求捕获配置
            session_name: 会话名称
        """
        self.browser_config = browser_config or DEFAULT_BROWSER_CONFIG
        self.turnstile_config = turnstile_config or DEFAULT_TURNSTILE_CONFIG
        self.capture_config = capture_config or DEFAULT_CAPTURE_CONFIG
        self.session_name = session_name
        
        # 请求捕获管理器
        self.capture_manager = RequestCaptureManager(session_name=session_name)
        
        # 浏览器实例（延迟初始化）
        self.driver: Optional[Driver] = None
        self.sb_context = None
        
        # 状态标记
        self._is_initialized = False
        self._turnstile_passed = False
        
        logger.info(f"CloudflareBypassSeleniumBase 初始化完成，会话: {session_name}")
    
    def start(self) -> "CloudflareBypassSeleniumBase":
        """
        启动浏览器
        
        返回:
            self（支持链式调用）
        """
        if self._is_initialized:
            logger.warning("浏览器已启动，跳过重复初始化")
            return self
        
        logger.info("正在启动 SeleniumBase UC Mode 浏览器...")
        
        # ------------------------------------------------------------
        # 配置浏览器启动参数
        # ------------------------------------------------------------
        user_agent = self.browser_config.user_agent or random.choice(USER_AGENTS)
        
        # 创建 Driver 实例
        self.driver = Driver(
            uc=True,  # 启用 Undetected ChromeDriver 模式
            headless=True,
            agent=user_agent,
            proxy=self.browser_config.proxy,
            # 启用性能日志以捕获网络请求
            enable_ws=True,
            chromium_arg="--no-sandbox,--disable-dev-shm-usage"
        )
        
        # 设置窗口大小
        self.driver.set_window_size(
            self.browser_config.window_width,
            self.browser_config.window_height
        )
        
        # 设置超时
        self.driver.set_page_load_timeout(self.browser_config.page_load_timeout)
        
        self._is_initialized = True
        logger.info("浏览器启动成功")
        
        return self
    
    def open_with_bypass(
        self,
        url: str,
        wait_time: float = 4.0,
        auto_click_turnstile: bool = True
    ) -> bool:
        """
        打开URL并自动绕过 Cloudflare 验证
        
        参数:
            url: 目标URL
            wait_time: 等待时间（秒）
            auto_click_turnstile: 是否自动点击 Turnstile
        
        返回:
            是否成功绕过
        """
        if not self._is_initialized:
            self.start()
        
        logger.info(f"正在打开URL: {url}")
        
        # ------------------------------------------------------------
        # 使用 UC 模式打开页面（带重连机制）
        # ------------------------------------------------------------
        try:
            self.driver.uc_open_with_reconnect(url, reconnect_time=wait_time)
        except Exception as e:
            logger.error(f"打开页面失败: {e}")
            return False
        
        # 等待页面加载
        self._human_delay(1.0, 2.0)
        
        # ------------------------------------------------------------
        # 检测并处理 Cloudflare 验证
        # ------------------------------------------------------------
        if auto_click_turnstile:
            for attempt in range(self.turnstile_config.max_retries):
                logger.info(f"检测 Cloudflare 验证 (尝试 {attempt + 1}/{self.turnstile_config.max_retries})")
                
                if self._detect_turnstile():
                    logger.info("检测到 Turnstile 验证码，正在尝试点击...")
                    
                    if self._click_turnstile():
                        self._turnstile_passed = True
                        logger.info("Turnstile 验证成功通过！")
                        break
                    else:
                        logger.warning(f"点击失败，等待重试...")
                        time.sleep(self.turnstile_config.retry_interval)
                else:
                    # 未检测到验证码，可能已通过或不需要验证
                    logger.info("未检测到 Turnstile 验证码，页面可能已通过验证")
                    self._turnstile_passed = True
                    break
        
        # 捕获 Cookie
        self._capture_cookies()
        
        return self._turnstile_passed
    
    def _detect_turnstile(self) -> bool:
        """
        检测页面是否存在 Turnstile 验证码
        
        返回:
            是否存在验证码
        """
        # ------------------------------------------------------------
        # 检测 Turnstile iframe
        # ------------------------------------------------------------
        turnstile_selectors = [
            "iframe[src*='challenges.cloudflare.com']",
            "iframe[src*='turnstile']",
            "div.cf-turnstile",
            "#cf-turnstile",
            "iframe[title*='Cloudflare']",
        ]
        
        for selector in turnstile_selectors:
            try:
                if self.driver.is_element_present(selector):
                    logger.debug(f"检测到 Turnstile 元素: {selector}")
                    return True
            except Exception:
                continue
        
        # 检测 Cloudflare 挑战页面
        try:
            page_source = self.driver.page_source.lower()
            challenge_indicators = [
                "just a moment",
                "checking your browser",
                "verify you are human",
                "cf-browser-verification",
                "cloudflare",
            ]
            
            for indicator in challenge_indicators:
                if indicator in page_source:
                    logger.debug(f"检测到挑战页面指示器: {indicator}")
                    return True
        except Exception:
            pass
        
        return False
    
    def _click_turnstile(self) -> bool:
        """
        点击 Turnstile 验证码
        
        返回:
            是否点击成功
        """
        # ------------------------------------------------------------
        # 方法1: 使用 SeleniumBase 内置的 GUI 点击方法
        # 这是最可靠的方法，使用 PyAutoGUI 进行操作系统级点击
        # ------------------------------------------------------------
        try:
            logger.info("尝试使用 uc_gui_click_captcha 方法...")
            
            # 添加人类思考延迟
            self._human_delay(
                self.turnstile_config.click_delay_min,
                self.turnstile_config.click_delay_max
            )
            
            # 使用 SeleniumBase 的 GUI 点击方法
            self.driver.uc_gui_click_captcha(
                frame="iframe",
                retry=False,
                blind=False
            )
            
            # 等待验证完成
            time.sleep(3)
            
            # 检查是否通过
            if not self._detect_turnstile():
                return True
            
        except Exception as e:
            logger.debug(f"uc_gui_click_captcha 失败: {e}")
        
        # ------------------------------------------------------------
        # 方法2: 使用键盘 Tab + Space 导航
        # ------------------------------------------------------------
        try:
            logger.info("尝试使用键盘导航方法...")
            
            # 模拟人类按键延迟
            self._human_delay(0.3, 0.8)
            
            # 按 Tab 键移动焦点到 Turnstile
            for _ in range(5):
                self.driver.uc_gui_press_key("Tab")
                self._human_delay(0.1, 0.3)
            
            # 按空格键选中
            self.driver.uc_gui_press_key("Space")
            
            time.sleep(3)
            
            if not self._detect_turnstile():
                return True
                
        except Exception as e:
            logger.debug(f"键盘导航方法失败: {e}")
        
        # ------------------------------------------------------------
        # 方法3: 直接定位并点击 iframe
        # ------------------------------------------------------------
        try:
            logger.info("尝试直接定位 iframe 方法...")
            
            # 查找 Turnstile iframe
            iframe = self.driver.find_element(
                By.CSS_SELECTOR,
                "iframe[src*='challenges.cloudflare.com'], iframe[src*='turnstile']"
            )
            
            if iframe:
                # 获取 iframe 位置
                location = iframe.location
                size = iframe.size
                
                # 计算点击坐标（iframe 中心偏左上，通常是 checkbox 位置）
                click_x = location['x'] + 30
                click_y = location['y'] + size['height'] // 2
                
                # 使用 GUI 坐标点击
                self.driver.uc_gui_click_x_y(click_x, click_y)
                
                time.sleep(3)
                
                if not self._detect_turnstile():
                    return True
                    
        except Exception as e:
            logger.debug(f"直接定位方法失败: {e}")
        
        return False
    
    def _human_delay(self, min_sec: float, max_sec: float) -> None:
        """添加拟人化延迟"""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
    
    def _capture_cookies(self) -> None:
        """捕获当前页面的所有 Cookie"""
        try:
            cookies = self.driver.get_cookies()
            self.capture_manager.capture_cookies(cookies)
            logger.info(f"捕获了 {len(cookies)} 个 Cookie")
        except Exception as e:
            logger.error(f"捕获 Cookie 失败: {e}")
    
    def get_cookies(self) -> List[Dict[str, Any]]:
        """
        获取当前所有 Cookie
        
        返回:
            Cookie 列表
        """
        if self.driver:
            return self.driver.get_cookies()
        return []
    
    def get_cookie_dict(self) -> Dict[str, str]:
        """
        获取 Cookie 字典（名称: 值）
        
        返回:
            Cookie 字典
        """
        cookies = self.get_cookies()
        return {c['name']: c['value'] for c in cookies}
    
    def get_cf_clearance(self) -> Optional[str]:
        """
        获取 cf_clearance Cookie（Cloudflare 验证通过标识）
        
        返回:
            cf_clearance 值
        """
        cookie_dict = self.get_cookie_dict()
        return cookie_dict.get('cf_clearance')
    
    def save_session(self, filename_prefix: Optional[str] = None) -> Dict[str, Path]:
        """
        保存会话数据（Cookie、请求等）
        
        参数:
            filename_prefix: 文件名前缀
        
        返回:
            保存的文件路径字典
        """
        # 先捕获最新的 Cookie
        self._capture_cookies()
        
        # 保存到文件
        return self.capture_manager.save_to_file(filename_prefix)
    
    def take_screenshot(self, filename: Optional[str] = None) -> Path:
        """
        截取当前页面截图
        
        参数:
            filename: 文件名（不含路径）
        
        返回:
            截图文件路径
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.session_name}_{timestamp}.png"
        
        filepath = SCREENSHOTS_DIR / filename
        self.driver.save_screenshot(str(filepath))
        logger.info(f"截图已保存: {filepath}")
        
        return filepath
    
    def execute_script(self, script: str, *args) -> Any:
        """
        执行 JavaScript 脚本
        
        参数:
            script: JavaScript 代码
            *args: 传递给脚本的参数
        
        返回:
            脚本执行结果
        """
        return self.driver.execute_script(script, *args)
    
    def get_page_source(self) -> str:
        """获取页面源码"""
        return self.driver.page_source
    
    def get_current_url(self) -> str:
        """获取当前URL"""
        return self.driver.current_url
    
    def close(self) -> None:
        """关闭浏览器"""
        if self.driver:
            try:
                # 保存会话数据
                self.save_session()
                
                # 关闭浏览器
                self.driver.quit()
                logger.info("浏览器已关闭")
            except Exception as e:
                logger.error(f"关闭浏览器时出错: {e}")
            finally:
                self.driver = None
                self._is_initialized = False
    
    def __enter__(self) -> "CloudflareBypassSeleniumBase":
        """上下文管理器入口"""
        return self.start()
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.close()


# ============================================================
# 便捷函数
# ============================================================

def bypass_and_get_cookies(
    url: str,
    proxy: Optional[str] = None,
    headless: bool = False,
    session_name: str = "quick_bypass"
) -> Dict[str, Any]:
    """
    便捷函数：绕过 Cloudflare 并获取 Cookie
    
    参数:
        url: 目标URL
        proxy: 代理地址
        headless: 是否无头模式
        session_name: 会话名称
    
    返回:
        包含 Cookie 和状态信息的字典
    """
    config = BrowserConfig(proxy=proxy, headless=headless)
    
    result = {
        "success": False,
        "url": url,
        "cookies": {},
        "cf_clearance": None,
        "saved_files": {},
        "error": None
    }
    
    try:
        with CloudflareBypassSeleniumBase(
            browser_config=config,
            session_name=session_name
        ) as bypass:
            
            if bypass.open_with_bypass(url):
                result["success"] = True
                result["cookies"] = bypass.get_cookie_dict()
                result["cf_clearance"] = bypass.get_cf_clearance()
                result["saved_files"] = bypass.save_session()
            else:
                result["error"] = "未能成功绕过 Cloudflare 验证"
                
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"绕过过程中出错: {e}")
    
    return result


# ============================================================
# 主程序入口
# ============================================================

if __name__ == "__main__":
    import argparse
    
    # 配置日志
    logger.add(
        "logs/seleniumbase_{time}.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG"
    )
    
    # 命令行参数
    parser = argparse.ArgumentParser(description="Cloudflare Turnstile 绕过工具 (SeleniumBase)")
    parser.add_argument("url", help="目标URL")
    parser.add_argument("--proxy", "-p", help="代理地址 (例如: http://127.0.0.1:7890)")
    parser.add_argument("--headless", "-hl", action="store_true", help="无头模式（不推荐）")
    parser.add_argument("--session", "-s", default="cli_session", help="会话名称")
    
    args = parser.parse_args()
    
    print("\n" + "="*60)
    print("Cloudflare Turnstile 绕过工具 (SeleniumBase UC Mode)")
    print("="*60 + "\n")
    
    result = bypass_and_get_cookies(
        url=args.url,
        proxy=args.proxy,
        headless=args.headless,
        session_name=args.session
    )
    
    if result["success"]:
        print("\n✅ 绕过成功！")
        print(f"\n📍 cf_clearance: {result['cf_clearance']}")
        print(f"\n🍪 Cookies ({len(result['cookies'])} 个):")
        for name, value in result['cookies'].items():
            print(f"   {name}: {value[:50]}..." if len(value) > 50 else f"   {name}: {value}")
        print(f"\n📁 保存的文件:")
        for file_type, path in result['saved_files'].items():
            print(f"   {file_type}: {path}")
    else:
        print(f"\n❌ 绕过失败: {result['error']}")
