"""
桌面边缘吸附快捷唤醒小程序 (Edge Cute Floating Dock)
- 默认在桌面边缘隐藏为一个极小、可爱的微型萌宠图标（🐱 38x38 圆角小猫咪图标）
- 鼠标放上去瞬间展开为超紧凑的快捷功能卡片
- 鼠标离开自动收缩为 38x38 纯图标，支持 📌 钉住模式
- 利用 macOS AppKit 原生系统级置顶（NSStatusWindowLevel + CanJoinAllSpaces），跨应用与全屏常驻
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
    屏幕边缘超紧凑萌宠快捷悬浮小窗（默认仅露出 38x38 小图标）
    """

    EXPANDED_WIDTH = 195
    EXPANDED_HEIGHT = 285
    ICON_SIZE = 38

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
        self._collapse_timer = None

        # 屏幕尺寸计算
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        # 居中 Y 坐标
        self.center_y = max(100, int(self.screen_height / 2))
        self.collapsed_y = self.center_y - self.ICON_SIZE // 2
        self.expanded_y = self.center_y - self.EXPANDED_HEIGHT // 2

        # 视觉主题配色
        self.bg_color = "#ffffff"
        self.badge_bg = "#6366f1"
        self.badge_hover_bg = "#4f46e5"
        self.text_primary = "#0f172a"
        self.text_secondary = "#64748b"

        self._build_ui()
        self._bind_events()

        # 初始设置为收起状态（仅 38x38 小图标）
        self._apply_collapsed_state()

        # 核心：配置 macOS 原生系统级全局置顶（跨所有应用/全屏桌面保持可见）
        self.root.after(100, self._set_macos_system_topmost)
        self.root.after(2000, self._maintain_macos_topmost)

        # 启动后检测一次浏览器状态
        self.root.after(500, self._check_browser_status_async)

    def _build_ui(self):
        """构建两套视图：1. 纯微型图标视图（收起时），2. 完整卡片视图（展开时）"""
        self.root.configure(bg=self.bg_color)

        # ═══════════════════════════════════════════════════════════
        # 视图 1：纯微型萌宠图标视图 (38x38)
        # ═══════════════════════════════════════════════════════════
        self.icon_badge_frame = tk.Frame(
            self.root,
            bg=self.badge_bg,
            cursor="hand2",
            highlightbackground="#818cf8",
            highlightthickness=1,
            bd=0
        )

        self.lbl_cute_icon = tk.Label(
            self.icon_badge_frame,
            text="🐱",
            font=("Helvetica", 17),
            bg=self.badge_bg,
            fg="#ffffff"
        )
        self.lbl_cute_icon.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # ═══════════════════════════════════════════════════════════
        # 视图 2：展开后的超紧凑核心快捷卡片面板 (195x285)
        # ═══════════════════════════════════════════════════════════
        self.card_frame = tk.Frame(
            self.root,
            bg=self.bg_color,
            highlightbackground="#818cf8",
            highlightthickness=1,
            bd=0,
            padx=7,
            pady=6
        )

        # 顶部标题栏：萌猫标题 + 状态小圆点 + 📌 钉住 + ✕
        header_row = tk.Frame(self.card_frame, bg=self.bg_color)
        header_row.pack(fill=tk.X, pady=(0, 4))

        self.status_dot = tk.Label(header_row, text="●", font=("Helvetica", 10), bg=self.bg_color, fg="#dc2626")
        self.status_dot.pack(side=tk.LEFT, padx=(0, 3))

        title_lbl = tk.Label(header_row, text="妙手萌盒 🐱", font=("Helvetica", 9, "bold"),
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
                self.card_frame,
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
            self.card_frame,
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
        """为收起的小图标与展开的卡片分别绑定鼠标事件"""
        # 图标视图：鼠标放上去就立即展开
        self.icon_badge_frame.bind("<Enter>", self._on_icon_enter, add="+")
        self.lbl_cute_icon.bind("<Enter>", self._on_icon_enter, add="+")

        # 卡片视图：鼠标滑入取消收起定时器，鼠标移出触发延迟收起
        self._bind_card_hover(self.card_frame)

    def _bind_card_hover(self, widget):
        widget.bind("<Enter>", self._on_card_enter, add="+")
        widget.bind("<Leave>", self._on_card_leave, add="+")
        for child in widget.winfo_children():
            self._bind_card_hover(child)

    def _apply_collapsed_state(self):
        """切换到贴边小图标形态 (38x38)"""
        self.is_expanded = False
        self.card_frame.pack_forget()
        self.icon_badge_frame.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.ICON_SIZE
        y = self.collapsed_y
        self.root.geometry(f"{self.ICON_SIZE}x{self.ICON_SIZE}+{x}+{y}")
        self._set_macos_system_topmost()

    def _apply_expanded_state(self):
        """切换到展开卡片形态 (195x285)"""
        self.is_expanded = True
        self.icon_badge_frame.pack_forget()
        self.card_frame.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.EXPANDED_WIDTH
        y = self.expanded_y
        self.root.geometry(f"{self.EXPANDED_WIDTH}x{self.EXPANDED_HEIGHT}+{x}+{y}")
        self._set_macos_system_topmost()

    def _on_icon_enter(self, event=None):
        """鼠标放上小猫咪图标：瞬间自动展开！"""
        if self._collapse_timer:
            self.root.after_cancel(self._collapse_timer)
            self._collapse_timer = None

        if not self.is_expanded:
            self._apply_expanded_state()

    def _on_card_enter(self, event=None):
        """鼠标在卡片内部移动：取消收起定时器"""
        if self._collapse_timer:
            self.root.after_cancel(self._collapse_timer)
            self._collapse_timer = None

    def _on_card_leave(self, event=None):
        """鼠标移出卡片：若未钉住则在 350ms 后自动收起为小图标"""
        if self.is_pinned:
            return

        if self._collapse_timer:
            self.root.after_cancel(self._collapse_timer)

        self._collapse_timer = self.root.after(350, self._check_and_collapse)

    def _check_and_collapse(self):
        """核查鼠标真实绝对坐标，若已离开卡片则收缩回 38x38 小图标"""
        self._collapse_timer = None
        if self.is_pinned:
            return

        mx = self.root.winfo_pointerx()
        my = self.root.winfo_pointery()

        wx = self.root.winfo_rootx()
        wy = self.root.winfo_rooty()
        ww = self.root.winfo_width()
        wh = self.root.winfo_height()

        # 如果鼠标仍在当前窗口内，不收起
        if wx <= mx <= wx + ww and wy <= my <= wy + wh:
            return

        if self.is_expanded:
            self._apply_collapsed_state()

    def _toggle_pin(self):
        """切换钉住锁定"""
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.btn_pin.configure(bg="#6366f1", fg="#ffffff", text="📌")
            if not self.is_expanded:
                self._apply_expanded_state()
        else:
            self.btn_pin.configure(bg="#f1f5f9", fg=self.text_secondary, text="📌")
            self._on_card_leave()

    def collapse_immediate(self):
        """立即收起回小图标"""
        self.is_pinned = False
        self.btn_pin.configure(bg="#f1f5f9", fg=self.text_secondary, text="📌")
        self._apply_collapsed_state()

    def _set_macos_system_topmost(self):
        """利用 macOS AppKit 原生接口将悬浮窗提升为全局系统级悬浮 (跨所有第三方应用与全屏桌面均保持可见)"""
        if sys.platform != "darwin":
            return
        try:
            import AppKit
            self.root.update_idletasks()

            for win in AppKit.NSApp.windows():
                # 排除主控制台窗口（主窗口高度较大 > 500）
                frame = win.frame()
                if frame.size.height < 450:
                    win.setLevel_(AppKit.NSStatusWindowLevel)
                    win.setCollectionBehavior_(
                        AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
                        AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary |
                        AppKit.NSWindowCollectionBehaviorStationary
                    )
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
