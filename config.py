# config.py - 严格类定义版
class BrowserConfig:
    headless = True
    user_agent = None
    proxy = None
    window_width = 1920
    window_height = 1080
    page_load_timeout = 30

class TurnstileConfig:
    max_retries = 3
    retry_interval = 2
    click_delay_min = 0.5
    click_delay_max = 1.5

class CaptureConfig:
    pass

# 定义默认实例
DEFAULT_BROWSER_CONFIG = BrowserConfig()
DEFAULT_TURNSTILE_CONFIG = TurnstileConfig()
DEFAULT_CAPTURE_CONFIG = CaptureConfig()

SCREENSHOTS_DIR = "/app/output"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]
