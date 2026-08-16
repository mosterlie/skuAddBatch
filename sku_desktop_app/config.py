"""
妙手 SKU 批量自动化录入助手 - 全局配置文件
"""
import os
import sys

# 确保本地 CDP 通信不走系统代理 (Clash/V2Ray 等)
os.environ["NO_PROXY"] = "127.0.0.1,localhost,::1"
os.environ["no_proxy"] = "127.0.0.1,localhost,::1"

# 默认 CDP 调试端口
DEFAULT_CDP_PORT = 9222
CDP_URL = f"http://127.0.0.1:{DEFAULT_CDP_PORT}"

# 获取应用运行根目录（兼容源码运行与 PyInstaller 打包后的 _MEIPASS 运行环境）
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

WEB_DIR = os.path.join(BASE_DIR, "web")
PLUGIN_DIR = os.path.join(WEB_DIR, "1688-Image-Downloader")
CALCFEE_DIR = os.path.join(WEB_DIR, "calcfee")

# 用户本地持久化浏览器数据目录（保存登录状态、Cookie，不与日常个人浏览器冲突）
if sys.platform == "darwin":
    # macOS
    USER_DATA_DIR = os.path.expanduser("~/Library/Application Support/MiaoshouSKUAssistant/UserData")
elif sys.platform == "win32":
    # Windows
    USER_DATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "MiaoshouSKUAssistant", "UserData")
else:
    # Linux / 其他
    USER_DATA_DIR = os.path.expanduser("~/.config/MiaoshouSKUAssistant/UserData")

# 妙手默认主页与特征关键字
MIAOSHOU_HOME_URL = "https://erp.91miaoshou.com/common_collect_box/items"
MIAOSHOU_URL_KEYWORDS = ["91miaoshou.com", "miaoshou.com", "erp", "item", "product", "goods"]
MIAOSHOU_PAGE_SELECTORS = [
    ".sale-attribute-list",
    ".pro-virtual-table",
    "input[placeholder*='平台SKU']",
    "input[placeholder*='商品基本价格']",
    ".product-picture-list",
    ".picture-draggable-list"
]

# 1688 默认主页与特征关键字
URL_1688_HOME = "https://www.1688.com/"
KEYWORDS_1688 = ["1688.com", "detail.1688.com", "offer"]

# 常见系统浏览器默认安装路径探测列表
CHROME_PATHS_MACOS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]

CHROME_PATHS_WINDOWS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]

# 支持的图片格式
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp')

# 超时与重试配置（毫秒/秒）
DEFAULT_TIMEOUT_MS = 15000
STEP_DELAY_SEC = 0.3
SCROLL_WAIT_SEC = 0.8
