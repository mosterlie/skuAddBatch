"""
桌面边缘吸附快捷唤醒小程序 (Edge Cute Floating Dock)
- 默认在桌面边缘隐藏为可爱的萌宠把手（🐱 萌猫），占用极小空间
- 利用 macOS AppKit 原生系统级置顶（NSStatusWindowLevel + CanJoinAllSpaces），切换到任何第三方应用（Chrome、微信、VSCode等）均常驻屏幕最前台可见
- 鼠标移动过去瞬间滑出精美的超紧凑快捷操作卡片
- 鼠标移开自动收起，支持 📌 钉住模式与一键直达
"""
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.browser_manager import BrowserManager


class FloatingDock:
    """
    屏幕边缘超紧凑萌系快捷唤醒小窗（跨应用全局常驻置顶）
    """

    EXPANDED_WIDTH = 195
    EXPANDED_HEIGHT = 285
    HANDLE_WIDTH = 32
    ANIM_STEPS = 6
    ANIM_INTERVAL_MS = 8

    def __init__(self, master=None, main_app=None, browser_mgr: Optional[BrowserManager] = None):
        self.main_app = main_app
        self.browser_mgr = browser_mgr or (main_app.browser_mgr if main_app else BrowserManager())
        self.is_standalone = master is None

        if self.is_standalone:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(master)

        # 窗口基础属性：无边框、全局置顶、半透明微调
        self.root.overrideredirect(True)
        try:
            self.root.attributes("-topmost", True)
        except Exception:
            pass
        if sys.platform == "darwin":
            try:
                self.root.attributes("-alpha", 0.96)
            except Exception:
                pass

        # 状态变量
        self.is_expanded = False
        self.is_pinned = False
        self._animating = False
        self._collapse_timer = None

        # 屏幕几何尺寸计算（右侧居中吸附）
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.pos_y = max(100, int((self.screen_height - self.EXPANDED_HEIGHT) / 2))

        self.x_collapsed = self.screen_width - self.HANDLE_WIDTH
        self.x_expanded = self.screen_width - self.EXPANDED_WIDTH
        self.current_x = self.x_collapsed

        # 初始定位在屏幕右侧收起位置
        self.root.geometry(f"{self.EXPANDED_WIDTH}x{self.EXPANDED_HEIGHT}+{self.current_x}+{self.pos_y}")

        # 视觉主题配色
        self.bg_color = "#ffffff"
        self.handle_bg = "#6366f1"
        self.text_primary = "#0f172a"
        self.text_secondary = "#64748b"

        self._build_ui()
        self._bind_events()

        # 核心：配置 macOS 原生系统级全局置顶（跨所有应用/全屏桌面保持可见）
        self.root.after(100, self._set_macos_system_topmost)
        self.root.after(2000, self._maintain_macos_topmost)

        # 启动后检测一次浏览器状态
        self.root.after(500, self._check_browser_status_async)

    def _set_macos_system_topmost(self):
        """利用 macOS AppKit 原生接口将悬浮窗提升为全局系统级悬浮 (跨所有第三方应用与全屏桌面均保持可见)"""
        if sys.platform != "darwin":
            return
        try:
            import AppKit
            self.root.update_idletasks()
            target_h = self.EXPANDED_HEIGHT

            for win in AppKit.NSApp.windows():
                frame = win.frame()
                if abs(frame.size.height - target_h) < 20:
                    # 提升到状态栏级/浮动窗口层级（高于普通应用和全屏 Chrome 窗口）
                    win.setLevel_(AppKit.NSStatusWindowLevel)
                    # 允许跨所有桌面 Space 共享、支持全屏辅助显示、固定不随切换丢失
                    win.setCollectionBehavior_(
                        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
                        AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary |
                        AppKit.NSWindowCollectionBehaviorStationary
                    )
                    # 彻底解决切换应用时悬浮窗消失的问题：切换应用时不隐藏！
                    win.setHidesOnDeactivate_(False)
        except Exception:
            pass

    def _maintain_macos_topmost(self):
        """定期维护系统置顶状态，防止偶发降级"""
        try:
            self._set_macos_system_topmost()
            self.root.lift()
        except Exception:
            pass
        self.root.after(3000, self._maintain_macos_topmost)

    def _build_ui(self):
        """构建超紧凑萌系悬浮小窗布局"""
        # 最外层容器
        self.outer_frame = tk.Frame(
            self.root,
            bg=self.bg_color,
            highlightbackground="#818cf8",
            highlightthickness=1,
            bd=0
        )
        self.outer_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 边缘萌宠把手 (Collapsed Handle - 可爱猫咪头像)
        self.handle_frame = tk.Frame(self.outer_frame, bg=self.handle_bg, width=self.HANDLE_WIDTH, cursor="hand2")
        self.handle_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.handle_frame.pack_propagate(False)

        # 把手内居中的萌宠图标与微型指示
        lbl_cat = tk.Label(self.handle_frame, text="🐱", font=("Helvetica", 14), bg=self.handle_bg, fg="#ffffff")
        lbl_cat.pack(pady=(10, 2))

        lbl_paw = tk.Label(self.handle_frame, text="🐾", font=("Helvetica", 10), bg=self.handle_bg, fg="#ffffff")
        lbl_paw.pack(pady=(2, 6))

        # 2. 展开后的超紧凑核心快捷卡片面板
        self.content_panel = tk.Frame(self.outer_frame, bg=self.bg_color, padx=6, pady=6)
        self.content_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 顶部标题栏：萌猫标题 + 状态小圆点 + 📌 钉住 + ✕
        header_row = tk.Frame(self.content_panel, bg=self.bg_color)
        header_row.pack(fill=tk.X, pady=(0, 4))

        self.status_dot = tk.Label(header_row, text="●", font=("Helvetica", 10), bg=self.bg_color, fg="#dc2626")
        self.status_dot.pack(side=tk.LEFT, padx=(0, 3))

        title_lbl = tk.Label(header_row, text="妙手萌盒", font=("Helvetica", 9, "bold"),
                             bg=self.bg_color, fg=self.text_primary)
        title_lbl.pack(side=tk.LEFT)

        btn_hide = tk.Button(
            header_row, text="✕", font=("Helvetica", 8, "bold"),
            bg="#f1f5f9", fg=self.text_secondary, relief="flat", bd=0, cursor="hand2",
            padx=3, pady=0, command=self.collapse_immediate
        )
        btn_hide.pack(side=tk.RIGHT)

        self.btn_pin = tk.Button(
            header_row, text="📌", font=("Helvetica", 8),
            bg="#f1f5f9", fg=self.text_secondary, relief="flat", bd=0, cursor="hand2",
            padx=3, pady=0, command=self._toggle_pin
        )
        self.btn_pin.pack(side=tk.RIGHT, padx=(0, 3))

        # 5 个紧凑精致胶囊按钮
        btn_configs = [
            ("🛒 1. 1688 货源", "#ea580c", "#ffffff", self._on_btn_1688),
            ("✨ 2. 素材采集", "#db2777", "#ffffff", self._on_btn_preview_1688),
            ("📊 3. SKU 核算", "#059669", "#ffffff", self._on_btn_calcfee),
            ("🚀 4. 打开妙手", "#2563eb", "#ffffff", self._on_btn_miaoshou),
            ("▶ 5. 批量录入", "#7c3aed", "#ffffff", self._on_btn_auto_execute),
        ]

        for text, bg_c, fg_c, cmd in btn_configs:
            btn = tk.Button(
                self.content_panel,
                text=text,
                font=("Helvetica", 9, "bold"),
                bg=bg_c,
                fg=fg_c,
                activebackground=bg_c,
                activeforeground=fg_c,
                highlightbackground=bg_c,
                relief="flat",
                bd=0,
                cursor="hand2",
                pady=4,
                anchor="w",
                padx=8,
                command=cmd
            )
            btn.pack(fill=tk.X, pady=2)

        # 底部展开主窗口按钮
        btn_show_main = tk.Button(
            self.content_panel,
            text="🖥️ 完整控制台",
            font=("Helvetica", 8, "bold"),
            bg="#f1f5f9",
            fg="#475569",
            activebackground="#e2e8f0",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=3,
            command=self._on_show_main_window
        )
        btn_show_main.pack(fill=tk.X, pady=(3, 0))

    def _bind_events(self):
        """递归绑定鼠标滑过与离开事件"""
        self._bind_hover_recursive(self.root)

    def _bind_hover_recursive(self, widget):
        widget.bind("<Enter>", self._on_mouse_enter, add="+")
        widget.bind("<Leave>", self._on_mouse_leave, add="+")
        for child in widget.winfo_children():
            self._bind_hover_recursive(child)

    def _on_mouse_enter(self, event=None):
        """鼠标滑入：立即瞬间平滑滑出展开"""
        if self._collapse_timer:
            self.root.after_cancel(self._collapse_timer)
            self._collapse_timer = None

        self._set_macos_system_topmost()
        if not self.is_expanded and not self._animating:
            self._animate_slide(target_x=self.x_expanded, on_done=lambda: setattr(self, 'is_expanded', True))

    def _on_mouse_leave(self, event=None):
        """鼠标滑出：若未钉住则在 350ms 后收起"""
        if self.is_pinned:
            return

        if self._collapse_timer:
            self.root.after_cancel(self._collapse_timer)

        self._collapse_timer = self.root.after(350, self._check_and_collapse)

    def _check_and_collapse(self):
        """核查鼠标坐标，若已离开窗口则平滑缩回边缘"""
        self._collapse_timer = None
        if self.is_pinned:
            return

        mx = self.root.winfo_pointerx()
        my = self.root.winfo_pointery()

        wx = self.root.winfo_rootx()
        wy = self.root.winfo_rooty()
        ww = self.root.winfo_width()
        wh = self.root.winfo_height()

        if wx <= mx <= wx + ww and wy <= my <= wy + wh:
            return

        if self.is_expanded and not self._animating:
            self._animate_slide(target_x=self.x_collapsed, on_done=lambda: setattr(self, 'is_expanded', False))

    def _animate_slide(self, target_x: int, on_done: Optional[Callable] = None):
        """轻快位移动画"""
        self._animating = True
        start_x = self.current_x
        diff = target_x - start_x
        step = diff / self.ANIM_STEPS
        current_step = 0

        def _step_fn():
            nonlocal current_step, start_x
            current_step += 1
            if current_step < self.ANIM_STEPS:
                new_x = int(start_x + step * current_step)
                self.current_x = new_x
                self.root.geometry(f"{self.EXPANDED_WIDTH}x{self.EXPANDED_HEIGHT}+{new_x}+{self.pos_y}")
                self.root.after(self.ANIM_INTERVAL_MS, _step_fn)
            else:
                self.current_x = target_x
                self.root.geometry(f"{self.EXPANDED_WIDTH}x{self.EXPANDED_HEIGHT}+{target_x}+{self.pos_y}")
                self._animating = False
                if on_done:
                    on_done()

        _step_fn()

    def _toggle_pin(self):
        """切换钉住锁定"""
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.btn_pin.configure(bg="#6366f1", fg="#ffffff", text="📌")
            if not self.is_expanded:
                self._animate_slide(target_x=self.x_expanded, on_done=lambda: setattr(self, 'is_expanded', True))
        else:
            self.btn_pin.configure(bg="#f1f5f9", fg=self.text_secondary, text="📌")
            self._on_mouse_leave()

    def collapse_immediate(self):
        """立即收起回边缘"""
        self.is_pinned = False
        self.btn_pin.configure(bg="#f1f5f9", fg=self.text_secondary, text="📌")
        self._animate_slide(target_x=self.x_collapsed, on_done=lambda: setattr(self, 'is_expanded', False))

    def _check_browser_status_async(self):
        """后台检测浏览器连接状态"""
        def _worker():
            ready = self.browser_mgr.is_cdp_ready()
            def _update():
                if ready:
                    self.status_dot.configure(fg="#16a34a")
                else:
                    self.status_dot.configure(fg="#dc2626")
            self.root.after(0, _update)

        threading.Thread(target=_worker, daemon=True).start()

    # ═══════════════════════════════════════════════════════════
    # 快捷按钮事件委托
    # ═══════════════════════════════════════════════════════════
    def _on_btn_1688(self):
        if self.main_app and hasattr(self.main_app, '_on_open_1688'):
            self.main_app._on_open_1688()
        else:
            def _w():
                if not self.browser_mgr.is_cdp_ready():
                    self.browser_mgr.launch_managed_chrome(config.URL_1688_HOME)
                else:
                    self.browser_mgr.open_new_tab(config.URL_1688_HOME)
                self._check_browser_status_async()
            threading.Thread(target=_w, daemon=True).start()

    def _on_btn_preview_1688(self):
        if self.main_app and hasattr(self.main_app, '_on_download_1688'):
            self.main_app._on_download_1688()
        else:
            self.browser_mgr.open_1688_extension_popup()
            self._check_browser_status_async()

    def _on_btn_calcfee(self):
        if self.main_app and hasattr(self.main_app, '_on_open_sku_calc'):
            self.main_app._on_open_sku_calc()
        else:
            self.browser_mgr.open_calcfee_popup()
            self._check_browser_status_async()

    def _on_btn_miaoshou(self):
        if self.main_app and hasattr(self.main_app, '_on_launch_browser'):
            self.main_app._on_launch_browser()
        else:
            def _w():
                if not self.browser_mgr.is_cdp_ready():
                    self.browser_mgr.launch_managed_chrome(config.MIAOSHOU_HOME_URL)
                else:
                    self.browser_mgr.open_new_tab(config.MIAOSHOU_HOME_URL)
                self._check_browser_status_async()
            threading.Thread(target=_w, daemon=True).start()

    def _on_btn_auto_execute(self):
        if self.main_app and hasattr(self.main_app, '_on_start_execution'):
            self._on_show_main_window()
            self.main_app._on_start_execution()
        else:
            messagebox.showinfo("提示", "请先在主控制台中选择 SKU 数据文件后执行录入！")

    def _on_show_main_window(self):
        """呼出主程序完整控制台窗口"""
        if self.main_app:
            try:
                if self.main_app.root.state() in ("iconic", "withdrawn"):
                    self.main_app.root.deiconify()
                    self.main_app.root.state("normal")
                self.main_app.root.lift()
                self.main_app.root.focus_force()
            except Exception:
                pass
        self.collapse_immediate()

    def show(self):
        self.root.deiconify()
        self.root.lift()
        self._set_macos_system_topmost()

    def hide(self):
        self.root.withdraw()


def launch_standalone_dock():
    dock = FloatingDock()
    dock.root.mainloop()


if __name__ == "__main__":
    launch_standalone_dock()
