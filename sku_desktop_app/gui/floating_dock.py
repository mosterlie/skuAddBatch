"""
桌面边缘吸附快捷唤醒小程序 (Edge Floating Dock)
支持默认贴边静默隐藏、鼠标滑过平滑滑出展开、核心按钮一键直达、钉住锁定与一键呼出主控制台。
"""
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.browser_manager import BrowserManager
from core.plugin_server import PluginServerManager


class FloatingDock:
    """
    屏幕边缘贴靠快捷唤醒悬浮岛
    """

    EXPANDED_WIDTH = 250
    EXPANDED_HEIGHT = 415
    HANDLE_WIDTH = 26
    ANIM_STEPS = 8
    ANIM_INTERVAL_MS = 12

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

        # 屏幕几何尺寸计算
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.pos_y = max(80, int((self.screen_height - self.EXPANDED_HEIGHT) / 2))

        self.x_collapsed = self.screen_width - self.HANDLE_WIDTH
        self.x_expanded = self.screen_width - self.EXPANDED_WIDTH
        self.current_x = self.x_collapsed

        # 初始定位在屏幕右侧收起位置
        self.root.geometry(f"{self.EXPANDED_WIDTH}x{self.EXPANDED_HEIGHT}+{self.current_x}+{self.pos_y}")

        # 视觉主题配色
        self.bg_color = "#ffffff"
        self.border_color = "#cbd5e1"
        self.text_primary = "#0f172a"
        self.text_secondary = "#64748b"

        self._build_ui()
        self._bind_events()

        # 启动后检测一次浏览器状态
        self.root.after(600, self._check_browser_status_async)

    def _build_ui(self):
        """构建悬浮岛 UI 布局 (包含左侧吸附把手 + 右侧核心卡片面板)"""
        # 最外层容器（含边框质感）
        self.outer_frame = tk.Frame(
            self.root,
            bg=self.bg_color,
            highlightbackground="#94a3b8",
            highlightthickness=1,
            bd=0
        )
        self.outer_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 边缘微型吸附把手 (Collapsed Handle)
        self.handle_frame = tk.Frame(self.outer_frame, bg="#2563eb", width=self.HANDLE_WIDTH, cursor="hand2")
        self.handle_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.handle_frame.pack_propagate(False)

        # 把手内竖排呼吸小标签
        lbl_icon = tk.Label(self.handle_frame, text="⚡", font=("Helvetica", 11), bg="#2563eb", fg="#ffffff")
        lbl_icon.pack(pady=(12, 4))

        handle_text = "快\n捷\n岛"
        lbl_txt = tk.Label(self.handle_frame, text=handle_text, font=("Helvetica", 9, "bold"),
                           bg="#2563eb", fg="#ffffff", justify=tk.CENTER)
        lbl_txt.pack(expand=True)

        # 2. 展开后的核心快捷卡片面板
        self.content_panel = tk.Frame(self.outer_frame, bg=self.bg_color, padx=10, pady=8)
        self.content_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 标题栏：小岛名称 + 钉住 + 隐藏/关闭
        header_row = tk.Frame(self.content_panel, bg=self.bg_color)
        header_row.pack(fill=tk.X, pady=(0, 6))

        title_lbl = tk.Label(header_row, text="⚡ 快捷悬浮工作台", font=("Helvetica", 10, "bold"),
                             bg=self.bg_color, fg=self.text_primary)
        title_lbl.pack(side=tk.LEFT)

        self.btn_pin = tk.Button(
            header_row, text="📌", font=("Helvetica", 9),
            bg="#f1f5f9", fg=self.text_secondary, relief="flat", bd=0, cursor="hand2",
            padx=4, pady=0, command=self._toggle_pin
        )
        self.btn_pin.pack(side=tk.RIGHT, padx=(4, 0))

        btn_hide = tk.Button(
            header_row, text="✕", font=("Helvetica", 9, "bold"),
            bg="#f1f5f9", fg=self.text_secondary, relief="flat", bd=0, cursor="hand2",
            padx=4, pady=0, command=self.collapse_immediate
        )
        btn_hide.pack(side=tk.RIGHT)

        # 状态指示胶囊行
        status_row = tk.Frame(self.content_panel, bg=self.bg_color)
        status_row.pack(fill=tk.X, pady=(0, 8))

        self.status_badge = tk.Label(
            status_row, text="🔴 未连接浏览器", font=("Helvetica", 8, "bold"),
            bg="#fee2e2", fg="#991b1b", padx=6, pady=2, relief="flat"
        )
        self.status_badge.pack(side=tk.LEFT)

        btn_refresh = tk.Button(
            status_row, text="🔄", font=("Helvetica", 8),
            bg="#f1f5f9", fg=self.text_primary, relief="flat", bd=0, cursor="hand2",
            padx=4, pady=1, command=self._check_browser_status_async
        )
        btn_refresh.pack(side=tk.RIGHT)

        # 分割线
        sep = tk.Frame(self.content_panel, bg="#e2e8f0", height=1)
        sep.pack(fill=tk.X, pady=(0, 8))

        # 快捷按钮组（6大高频操作）
        btn_configs = [
            ("🛒 1. 打开 1688 货源", "#f97316", "#ffffff", self._on_btn_1688),
            ("✨ 2. 1688 数据预览采集", "#ec4899", "#ffffff", self._on_btn_preview_1688),
            ("📊 3. 弹出 SKU 核算台", "#10b981", "#ffffff", self._on_btn_calcfee),
            ("🚀 4. 打开妙手工作台", "#3b82f6", "#ffffff", self._on_btn_miaoshou),
            ("▶ 5. 一键全自动批量录入", "#8b5cf6", "#ffffff", self._on_btn_auto_execute),
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
                pady=6,
                anchor="w",
                padx=8,
                command=cmd
            )
            btn.pack(fill=tk.X, pady=3)

        # 底部展开主窗口按钮
        sep2 = tk.Frame(self.content_panel, bg="#e2e8f0", height=1)
        sep2.pack(fill=tk.X, pady=(6, 6))

        btn_show_main = tk.Button(
            self.content_panel,
            text="🖥️ 展开完整控制台",
            font=("Helvetica", 9, "bold"),
            bg="#f1f5f9",
            fg="#1e293b",
            activebackground="#e2e8f0",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=5,
            command=self._on_show_main_window
        )
        btn_show_main.pack(fill=tk.X)

    def _bind_events(self):
        """绑定鼠标移入唤醒与移出延迟收起事件"""
        self._bind_hover_recursive(self.root)

    def _bind_hover_recursive(self, widget):
        widget.bind("<Enter>", self._on_mouse_enter, add="+")
        widget.bind("<Leave>", self._on_mouse_leave, add="+")
        for child in widget.winfo_children():
            self._bind_hover_recursive(child)

    def _on_mouse_enter(self, event=None):
        """鼠标滑入：取消收起定时器并触发平滑滑出展开"""
        if self._collapse_timer:
            self.root.after_cancel(self._collapse_timer)
            self._collapse_timer = None

        if not self.is_expanded and not self._animating:
            self._animate_slide(target_x=self.x_expanded, on_done=lambda: setattr(self, 'is_expanded', True))

    def _on_mouse_leave(self, event=None):
        """鼠标滑出：若未钉住则启动 400ms 缓冲后收起"""
        if self.is_pinned:
            return

        if self._collapse_timer:
            self.root.after_cancel(self._collapse_timer)

        self._collapse_timer = self.root.after(420, self._check_and_collapse)

    def _check_and_collapse(self):
        """核查鼠标真实坐标，若已离开窗口则平滑收起"""
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
        """丝滑步进位移动画"""
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
        """切换钉住锁定状态"""
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.btn_pin.configure(bg="#2563eb", fg="#ffffff", text="📌")
            if not self.is_expanded:
                self._animate_slide(target_x=self.x_expanded, on_done=lambda: setattr(self, 'is_expanded', True))
        else:
            self.btn_pin.configure(bg="#f1f5f9", fg=self.text_secondary, text="📌")
            self._on_mouse_leave()

    def collapse_immediate(self):
        """立即平滑收缩回边缘"""
        self.is_pinned = False
        self.btn_pin.configure(bg="#f1f5f9", fg=self.text_secondary, text="📌")
        self._animate_slide(target_x=self.x_collapsed, on_done=lambda: setattr(self, 'is_expanded', False))

    def _check_browser_status_async(self):
        """后台异步检测 CDP 浏览器运行状态并刷新 Badge"""
        def _worker():
            ready = self.browser_mgr.is_cdp_ready()
            tab_cnt = self.browser_mgr.get_open_tab_count() if ready else 0

            def _update():
                if ready:
                    self.status_badge.configure(
                        text=f"🟢 浏览器已连接 ({tab_cnt}页)",
                        bg="#dcfce7",
                        fg="#166534"
                    )
                else:
                    self.status_badge.configure(
                        text="🔴 浏览器未连接",
                        bg="#fee2e2",
                        fg="#991b1b"
                    )
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
        """呼出/还原主程序完整控制台窗口"""
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

    def hide(self):
        self.root.withdraw()


def launch_standalone_dock():
    """独立调试启动入口"""
    dock = FloatingDock()
    dock.root.mainloop()


if __name__ == "__main__":
    launch_standalone_dock()
