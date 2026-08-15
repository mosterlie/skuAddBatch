"""
浏览器生命周期管理与 CDP 接管核心模块（线程安全与单线程 Playwright 调度架构）
"""
import os
import sys
import time
import queue
import threading
import subprocess
import urllib.request
import json
from typing import List, Dict, Optional, Tuple, Any, Callable
from dataclasses import dataclass

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


@dataclass
class TabInfo:
    """标签页信息模型"""
    index: int
    title: str
    url: str
    is_miaoshou: bool
    is_1688: bool
    page: Page
    is_active: bool = False

    def display_text(self) -> str:
        if self.is_miaoshou:
            tag = "🎯 [妙手编辑页]"
        elif self.is_1688:
            tag = "🛒 [1688工作台/商品]"
        else:
            tag = "[其他网页]"
        active_mark = " 👁当前显示" if self.is_active else ""
        short_title = self.title if len(self.title) <= 30 else self.title[:28] + "..."
        return f"{tag} {short_title} ({self.url[:40]}...){active_mark}"


class BrowserManager:
    """
    负责启动 Chrome 实例、探测 CDP 端口、管理 Playwright 连接与标签页识别。
    内部维护常驻工作线程，确保所有 Playwright 调用都在同一原生线程中执行，彻底杜绝 Greenlet 跨线程异常。
    """

    def __init__(self, port: int = config.DEFAULT_CDP_PORT, user_data_dir: str = config.USER_DATA_DIR):
        self.port = port
        self.cdp_url = f"http://127.0.0.1:{self.port}"
        self.user_data_dir = user_data_dir
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None

        self._task_queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="PlaywrightWorkerThread")
        self._thread.start()

    def _worker_loop(self):
        """Playwright 专属常驻工作线程循环"""
        try:
            self.playwright = sync_playwright().start()
        except Exception as e:
            print(f"[BrowserManager] Playwright init failed: {e}")

        while True:
            item = self._task_queue.get()
            if item is None:
                break
            func, args, kwargs, fut = item
            try:
                result = func(*args, **kwargs)
                fut["result"] = result
                fut["success"] = True
            except Exception as e:
                fut["error"] = e
                fut["success"] = False
            finally:
                fut["event"].set()
                self._task_queue.task_done()

    def run_on_browser_thread(self, func: Callable, *args, timeout: Optional[float] = None, **kwargs) -> Any:
        """安全派发函数到 Playwright 专属常驻线程中同步执行"""
        fut = {"result": None, "error": None, "success": False, "event": threading.Event()}
        self._task_queue.put((func, args, kwargs, fut))
        if timeout:
            if not fut["event"].wait(timeout=timeout):
                raise TimeoutError("Playwright thread execution timeout")
        else:
            fut["event"].wait()

        if not fut["success"]:
            raise fut["error"]
        return fut["result"]

    @staticmethod
    def detect_browser_executable() -> Optional[str]:
        """跨平台自动探测系统中已安装的 Chrome 或 Edge 浏览器绝对路径"""
        if sys.platform == "darwin":
            for p in config.CHROME_PATHS_MACOS:
                if os.path.exists(p):
                    return p
        elif sys.platform == "win32":
            for p in config.CHROME_PATHS_WINDOWS:
                if os.path.exists(p):
                    return p
            # 注册表查询
            try:
                import winreg
                keys = [
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe"),
                    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                ]
                for root_k, sub_k in keys:
                    try:
                        with winreg.OpenKey(root_k, sub_k) as k:
                            val, _ = winreg.QueryValueEx(k, "")
                            if val and os.path.exists(val):
                                return val
                    except Exception:
                        continue
            except ImportError:
                pass
        else:
            for p in config.CHROME_PATHS_LINUX:
                if os.path.exists(p):
                    return p
        return None

    def is_cdp_ready(self) -> bool:
        """检查指定 CDP 端口是否已处于监听响应状态"""
        try:
            req = urllib.request.Request(f"{self.cdp_url}/json/version", headers={"User-Agent": "Mozilla/5.0"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            return False
        return False

    def bring_browser_to_front(self):
        """将 Chrome 浏览器窗口激活并置于前台"""
        if sys.platform == "darwin":
            os.system('''osascript -e 'tell application "Google Chrome" to activate' 2>/dev/null''')

    def _get_front_window_active_url(self) -> Optional[str]:
        """
        macOS 精确方案：通过 AppleScript 读取浏览器最前窗口中『真正正在显示』页签的 URL。
        规避 visibilityState 在会话恢复页签/多窗口场景下误报 visible 的问题。
        """
        if sys.platform != "darwin":
            return None
        for app_name in ("Google Chrome", "Microsoft Edge"):
            try:
                script = f'''
                tell application "{app_name}"
                    repeat with w in windows
                        try
                            set u to URL of active tab of w
                            if u does not contain "127.0.0.1" and u does not contain "localhost" then
                                return u
                            end if
                        end try
                    end repeat
                end tell
                '''
                out = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
                url = (out.stdout or "").strip()
                if url:
                    return url
            except Exception:
                continue
        return None

    @staticmethod
    def _normalize_url(u: str) -> str:
        """URL 归一化，忽略 hash 与结尾斜杠差异"""
        return (u or "").split("#")[0].rstrip("/")

    def get_open_tab_count(self) -> int:
        """获取当前浏览器中实际存在的页面标签数量"""
        try:
            req = urllib.request.Request(f"{self.cdp_url}/json/list", headers={"User-Agent": "Mozilla/5.0"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=1.5) as resp:
                if resp.status == 200:
                    tabs = json.loads(resp.read().decode('utf-8'))
                    return len([t for t in tabs if t.get('type') == 'page'])
        except Exception:
            pass
        return 0

    def create_tab_via_cdp_http(self, url: str) -> bool:
        """通过 CDP HTTP 接口在浏览器中直接拉起新窗口/标签页"""
        try:
            req = urllib.request.Request(f"{self.cdp_url}/json/new?{url}", method="PUT", headers={"User-Agent": "Mozilla/5.0"})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(req, timeout=2.0) as resp:
                if resp.status == 200:
                    time.sleep(0.3)
                    self.bring_browser_to_front()
                    return True
        except Exception:
            pass
        return False

    def _ensure_session_retention_preferences(self):
        """配置 Chrome 偏好设置：启用『从上次停下的地方继续』，永久保留 Session Cookie 与登录态，阻止退出时会话被清空"""
        default_dir = os.path.join(self.user_data_dir, "Default")
        os.makedirs(default_dir, exist_ok=True)
        pref_file = os.path.join(default_dir, "Preferences")

        prefs = {}
        if os.path.exists(pref_file):
            try:
                with open(pref_file, "r", encoding="utf-8") as f:
                    prefs = json.load(f)
            except Exception:
                prefs = {}

        if "session" not in prefs:
            prefs["session"] = {}
        prefs["session"]["restore_on_startup"] = 1

        if "profile" not in prefs:
            prefs["profile"] = {}
        prefs["profile"]["exit_type"] = "Normal"
        prefs["profile"]["exited_cleanly"] = True

        try:
            with open(pref_file, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def launch_managed_chrome(self, initial_url: str = config.MIAOSHOU_HOME_URL) -> Tuple[bool, str]:
        """以长效持久化配置和远程调试端口拉起独立的 Chrome/Edge 浏览器"""
        if self.is_cdp_ready():
            tab_cnt = self.get_open_tab_count()
            if tab_cnt == 0:
                self.create_tab_via_cdp_http(initial_url)
                self.bring_browser_to_front()
                return True, "检测到后台浏览器无活动窗口，已自动唤起新窗口！"
            else:
                self.open_or_focus_url(initial_url)
                self.bring_browser_to_front()
                return True, f"浏览器已处于调试模式运行中 (当前 {tab_cnt} 个窗口)"

        chrome_path = self.detect_browser_executable()
        if not chrome_path:
            return False, "未能在当前系统中检测到 Chrome 或 Edge 浏览器，请检查是否已安装！"

        os.makedirs(self.user_data_dir, exist_ok=True)
        self._ensure_session_retention_preferences()

        args = [
            chrome_path,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.user_data_dir}",
            "--restore-last-session",
            "--hide-crash-restore-bubble",
            "--disable-session-crashed-bubble",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
            initial_url
        ]

        ext_path = "/Users/gx/Desktop/mypro/1688-Image-Downloader"
        if os.path.exists(ext_path):
            args.insert(1, f"--load-extension={ext_path}")
            args.insert(2, f"--disable-extensions-except={ext_path}")

        try:
            if sys.platform == "win32":
                subprocess.Popen(args, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            
            for _ in range(20):
                time.sleep(0.5)
                if self.is_cdp_ready():
                    self.bring_browser_to_front()
                    return True, f"成功启动并连接专用工作浏览器 (端口: {self.port})"

            return False, "浏览器已启动，但调试端口响应超时，请重试！"
        except Exception as e:
            return False, f"拉起浏览器失败: {str(e)}"

    def connect(self, activate: bool = True, auto_create_tab: bool = True) -> Tuple[bool, str]:
        """连接到当前正在运行的 Chrome CDP 调试服务（在专属工作线程中执行）

        activate: 连接成功后是否将浏览器窗口拉到前台
        auto_create_tab: 无标签页时是否自动新建妙手主页标签
        """
        return self.run_on_browser_thread(self._connect_impl, activate, auto_create_tab)

    def _connect_impl(self, activate: bool = True, auto_create_tab: bool = True) -> Tuple[bool, str]:
        if not self.is_cdp_ready():
            return False, f"未检测到运行中的调试浏览器 (端口: {self.port})，请先点击【启动浏览器】"

        if auto_create_tab and self.get_open_tab_count() == 0:
            self.create_tab_via_cdp_http(config.MIAOSHOU_HOME_URL)

        try:
            if not self.playwright:
                self.playwright = sync_playwright().start()

            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
            if not self.browser.contexts:
                return False, "已连接到 CDP，但未找到可用的浏览器上下文 (Context)"

            self.context = self.browser.contexts[0]
            
            # 自动绑定弹窗处理器，避免浏览器 alert/confirm/beforeunload 引发未捕获协议异常
            def _bind_dialog_handler(page: Page):
                try:
                    page.on("dialog", lambda dialog: self._safe_handle_dialog(dialog))
                except Exception:
                    pass

            self.context.on("page", lambda p: _bind_dialog_handler(p))
            for p in self.context.pages:
                _bind_dialog_handler(p)

            if activate:
                self.bring_browser_to_front()
            return True, "成功接管 Chrome 浏览器！"
        except Exception as e:
            return False, f"连接 Chrome 失败: {str(e)}"

    @staticmethod
    def _safe_handle_dialog(dialog):
        """安全处理网页原生弹窗 (alert/confirm/prompt)"""
        try:
            dialog.accept()
        except Exception:
            pass

    def get_all_tabs(self) -> List[TabInfo]:
        """获取当前浏览器中所有已打开的标签页"""
        return self.run_on_browser_thread(self._get_all_tabs_impl)

    def _get_all_tabs_impl(self) -> List[TabInfo]:
        if not self.context:
            ok, msg = self._connect_impl(activate=False, auto_create_tab=False)
            if not ok or not self.context:
                return []

        # 主方案：macOS 用 AppleScript 获取最前窗口真实显示的页签 URL
        front_active_url = self._get_front_window_active_url()

        tabs = []
        js_states = []  # 与 tabs 平行的 (visible_state, has_focus) 记录，用于兜底判定
        for idx, p in enumerate(self.context.pages):
            try:
                title = p.title()
                url = p.url

                is_url_match = any(kw in url.lower() for kw in config.MIAOSHOU_URL_KEYWORDS)
                is_title_match = "妙手" in title or "商品" in title or "发布" in title or "编辑" in title
                has_dom_match = False
                if is_url_match or is_title_match or "127.0.0.1" in url or "localhost" in url or url.startswith("file:"):
                    try:
                        dom_count = p.locator(".sale-attribute-list, .pro-virtual-table, input[placeholder*='平台SKU']").count()
                        if dom_count > 0:
                            has_dom_match = True
                    except Exception:
                        pass

                is_1688 = (any(kw in url.lower() for kw in config.KEYWORDS_1688) or ("1688" in title and "127.0.0.1" not in url)) and "127.0.0.1" not in url and "localhost" not in url
                is_target = is_url_match and (is_title_match or has_dom_match) or has_dom_match

                # 记录 JS 侧可见性状态（兜底用，不直接作为结论）
                visible_state, has_focus = "", False
                try:
                    visible_state = p.evaluate("() => document.visibilityState") or ""
                    has_focus = bool(p.evaluate("() => document.hasFocus()"))
                except Exception:
                    pass

                tabs.append(TabInfo(
                    index=idx,
                    title=title or "未命名标签页",
                    url=url,
                    is_miaoshou=is_target,
                    is_1688=is_1688,
                    page=p,
                    is_active=False
                ))
                js_states.append((visible_state, has_focus))
            except Exception:
                continue

        # 判定激活页签：AppleScript URL 精确匹配 -> JS 聚焦态 -> 唯一可见页
        active_idx = -1
        if front_active_url:
            norm_target = self._normalize_url(front_active_url)
            for i, t in enumerate(tabs):
                if self._normalize_url(t.url) == norm_target:
                    active_idx = i
                    break
        if active_idx < 0 and js_states:
            # 过滤掉本地插件弹窗（127.0.0.1 或 localhost），不让它抢占 active_idx
            valid_indices = [
                i for i, t in enumerate(tabs) 
                if "127.0.0.1" not in (t.url or "") and "localhost" not in (t.url or "")
            ]
            focused = [i for i in valid_indices if js_states[i][1]]
            visible = [i for i in valid_indices if js_states[i][0] == "visible"]
            
            if focused:
                active_idx = focused[0]
            elif len(visible) == 1:
                active_idx = visible[0]

        if 0 <= active_idx < len(tabs):
            tabs[active_idx].is_active = True

        return tabs

    def open_new_tab(self, target_url: str) -> Optional[Page]:
        """在 Chrome 中强制开启新标签页，总是在最右侧打开"""
        return self.run_on_browser_thread(self._open_new_tab_impl, target_url)

    def _open_new_tab_impl(self, target_url: str) -> Optional[Page]:
        if not self.context:
            ok, _ = self._connect_impl()
            if not ok or not self.context:
                return None
        self.create_tab_via_cdp_http(target_url)
        # 浏览器通过 /json/new 创建标签页后会自动聚焦，不需要手动调用 bring_to_front()
        # 否则如果 Playwright 的 context.pages 同步有延迟，pages[-1] 可能是旧页面，导致跳回旧页面
        time.sleep(0.5)
        self.bring_browser_to_front()
        
        if self.context.pages:
            return self.context.pages[-1]
        return None

    def open_or_focus_url(self, target_url: str) -> Optional[Page]:
        """在 Chrome 中打开目标网址或激活已有标签页"""
        return self.run_on_browser_thread(self._open_or_focus_url_impl, target_url)

    def _open_or_focus_url_impl(self, target_url: str) -> Optional[Page]:
        created_tab = False
        if self.get_open_tab_count() == 0:
            created_tab = self.create_tab_via_cdp_http(target_url)
            if created_tab:
                time.sleep(0.8)  # 等待新标签开始加载目标 URL，避免后续 URL 匹配失败导致重复开页

        if not self.context:
            ok, _ = self._connect_impl()
            if not ok or not self.context:
                return None

        # CDP 已创建好目标标签页：直接定位并返回它，不再重复开页
        if created_tab:
            norm_target = self._normalize_url(target_url)
            for p in self.context.pages:
                try:
                    if self._normalize_url(p.url) == norm_target or target_url in p.url:
                        return p
                except Exception:
                    continue
            # 加载中 URL 尚未就绪：返回最后一个页面（即刚创建的）
            if self.context.pages:
                return self.context.pages[-1]
            return None

        # 1. 优先检索已有相同域名的标签页，直接置顶切换，避免重复开页
        norm_target = self._normalize_url(target_url)
        for p in self.context.pages:
            try:
                if self._normalize_url(p.url) == norm_target or (target_url != "about:blank" and target_url in p.url):
                    p.bring_to_front()
                    self.bring_browser_to_front()
                    return p
            except Exception:
                continue

        # 2. 复用空白页（如刚启动时的 about:blank）
        for p in self.context.pages:
            try:
                if p.url in ("about:blank", "") or "newtab" in p.url or "new-tab-page" in p.url:
                    try:
                        p.on("dialog", lambda dialog: self._safe_handle_dialog(dialog))
                    except Exception:
                        pass
                    try:
                        p.goto(target_url, wait_until="commit", timeout=10000)
                    except Exception:
                        pass
                    p.bring_to_front()
                    self.bring_browser_to_front()
                    return p
            except Exception:
                continue

        # 3. 新建标签页秒级直达
        try:
            new_p = self.context.new_page()
            try:
                new_p.on("dialog", lambda dialog: self._safe_handle_dialog(dialog))
            except Exception:
                pass
            try:
                new_p.goto(target_url, wait_until="commit", timeout=10000)
            except Exception:
                pass
            new_p.bring_to_front()
            self.bring_browser_to_front()
            return new_p
        except Exception:
            return None

    def get_active_page(self) -> Optional[Page]:
        """获取当前正在显示（激活）的页签对应的 Page 对象；窗口最小化等场景下全部 hidden 时返回 None"""
        return self.run_on_browser_thread(self._get_active_page_impl)

    def _get_active_page_impl(self) -> Optional[Page]:
        tabs = self._get_all_tabs_impl()
        for t in tabs:
            if t.is_active:
                return t.page
        return None

    def find_best_target_page(self) -> Optional[Page]:
        """自动从当前浏览器所有标签页中找到最匹配的妙手页面或活动标签页"""
        return self.run_on_browser_thread(self._find_best_target_page_impl)

    def _find_best_target_page_impl(self) -> Optional[Page]:
        if not self.context:
            ok, _ = self._connect_impl()
            if not ok or not self.context:
                return None

        for p in self.context.pages:
            try:
                url = p.url.lower()
                title = p.title()
                if "91miaoshou.com" in url or "miaoshou.com" in url or "妙手" in title:
                    return p
            except Exception:
                continue

        if self.context.pages:
            return self.context.pages[0]

    def open_1688_extension_popup(self, target_tab_id: Optional[int] = None) -> bool:
        """唤起 1688-Image-Downloader 插件原生独立弹窗窗口 (方案 A)"""
        from core.plugin_server import PluginServerManager
        PluginServerManager.start_server(self, 31416)
        popup_url = PluginServerManager.get_popup_url()

        # 检查是否已打开插件窗口/页签
        tabs = self.get_all_tabs()
        for t in tabs:
            if "popup.html" in (t.url or ""):
                def _refresh_and_focus(page=t.page):
                    page.bring_to_front()
                    # 尝试直接调用页面的重新扫描函数，无刷新体验更好
                    # 注意：必须用 setTimeout 包裹，否则 evaluate 会 await 它的 Promise，
                    # 导致后端 executor 线程死锁 (等待 fetch /api/scan, 而 fetch 等待 executor)
                    try:
                        page.evaluate("setTimeout(() => { try { if(typeof window.performScan === 'function') window.performScan(); } catch(e){} }, 10);")
                    except Exception:
                        pass
                self.run_on_browser_thread(_refresh_and_focus)
                self.bring_browser_to_front()
                return True

        # 优先在当前活动 1688 页面中通过 window.open 唤出独立窗口 (width=920, height=720)
        opened = False
        active_p = self.get_active_page() or (tabs[-1].page if tabs else None)
        if active_p:
            try:
                def _open(p=active_p):
                    p.evaluate(f"""() => {{
                        const w = window.open('{popup_url}', '1688_downloader_popup_win', 'width=920,height=720,left=150,top=100,menubar=no,toolbar=no,location=no,status=no,resizable=yes');
                        if (w) w.focus();
                    }}""")
                self.run_on_browser_thread(_open)
                opened = True
            except Exception:
                opened = False

        if not opened:
            self.create_tab_via_cdp_http(popup_url)

        self.bring_browser_to_front()
        return True

    def open_calcfee_popup(self) -> bool:
        """唤起 SKU 录入与核算系统原生独立弹窗窗口"""
        from core.plugin_server import PluginServerManager
        PluginServerManager.start_server(self, 31416)
        calcfee_url = PluginServerManager.get_calcfee_url()

        # 检查是否已打开计算器窗口/页签
        tabs = self.get_all_tabs()
        for t in tabs:
            if "calcfee" in t.url or "calcfee_ui" in (t.title or ""):
                self.run_on_browser_thread(t.page.bring_to_front)
                self.bring_browser_to_front()
                return True

        # 优先在当前活动页面中通过 window.open 唤出独立窗口 (width=1320, height=850)
        opened = False
        active_p = self.get_active_page() or (tabs[-1].page if tabs else None)
        if active_p:
            try:
                def _open(p=active_p):
                    p.evaluate(f"""() => {{
                        const w = window.open('{calcfee_url}', 'calcfee_popup_win', 'width=1320,height=850,left=100,top=60,menubar=no,toolbar=no,location=no,status=no,resizable=yes');
                        if (w) w.focus();
                    }}""")
                self.run_on_browser_thread(_open)
                opened = True
            except Exception:
                opened = False

        if not opened:
            self.create_tab_via_cdp_http(calcfee_url)

        self.bring_browser_to_front()
        return True

    def close(self):
        """释放 Playwright 资源"""
        self._task_queue.put(None)
