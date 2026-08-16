"""
桌面边缘吸附快捷唤醒小程序 (Edge 3-Tier Cute Floating Dock)
- 默认状态 (Tier 1)：屏幕边缘仅显示极小的一点 (8px 宽度的微型指示条)，完全零遮挡；
- 鼠标滑过 (Tier 2)：鼠标移动到边缘微点时，瞬间浮现出可爱的 🐱 萌猫小图标；
- 点击图标 (Tier 3)：点击 🐱 猫咪图标，立即弹出完整的快捷操作工作台卡片；
- 鼠标离开自动平滑缩回，支持 📌 钉住锁定与全系统置顶常驻。
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
    三级渐进式边缘悬浮小窗：极小微点 ➔ 萌宠图标 ➔ 点击弹出操作卡片
    """

    DOT_WIDTH = 8
    DOT_HEIGHT = 32

    ICON_SIZE = 40

    CARD_WIDTH = 195
    CARD_HEIGHT = 285

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

        # 状态变量: 'dot' | 'icon' | 'card'
        self.current_state = "dot"
        self.is_pinned = False
        self._outside_count = 0

        # 屏幕尺寸计算
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.center_y = max(120, int(self.screen_height / 2))

        # 各形态 Y 坐标
        self.dot_y = self.center_y - self.DOT_HEIGHT // 2
        self.icon_y = self.center_y - self.ICON_SIZE // 2
        self.card_y = self.center_y - self.CARD_HEIGHT // 2

        # 视觉主题配色
        self.bg_color = "#ffffff"
        self.accent_color = "#6366f1"
        self.text_primary = "#0f172a"
        self.text_secondary = "#64748b"

        self._build_ui()
        self._bind_events()

        # 默认形态：极小边缘微点
        self._switch_to_dot_state()

        # 核心 1：启动 40ms 全局硬件鼠标探针
        self.root.after(100, self._global_mouse_watcher)

        # 核心 2：配置 macOS 原生系统级全局置顶（跨所有应用/全屏桌面保持可见）
        self.root.after(150, self._set_macos_system_topmost)
        self.root.after(2500, self._maintain_macos_topmost)

        # 启动后检测一次浏览器状态
        self.root.after(500, self._check_browser_status_async)

    def _build_ui(self):
        """构建三级视图容器"""
        self.root.configure(bg=self.bg_color)

        # ═══════════════════════════════════════════════════════════
        # 视图 1：极小边缘微点 (8x32)
        # ═══════════════════════════════════════════════════════════
        self.dot_frame = tk.Frame(
            self.root,
            bg=self.accent_color,
            cursor="hand2"
        )

        # ═══════════════════════════════════════════════════════════
        # 视图 2：萌宠小图标 (40x40 🐱 猫咪徽章)
        # ═══════════════════════════════════════════════════════════
        self.icon_frame = tk.Frame(
            self.root,
            bg=self.accent_color,
            cursor="hand2",
            highlightbackground="#818cf8",
            highlightthickness=1,
            bd=0
        )

        self.lbl_cute_icon = tk.Label(
            self.icon_frame,
            text="🐱",
            font=("Helvetica", 19),
            bg=self.accent_color,
            fg="#ffffff",
            cursor="hand2"
        )
        self.lbl_cute_icon.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # ═══════════════════════════════════════════════════════════
        # 视图 3：点击后展开的操作页面卡片 (195x285)
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
            padx=3, pady=0, command=self._switch_to_dot_state
        )
        btn_hide.pack(side=tk.RIGHT)

        self.btn_pin = tk.Button(
            header_row, text="📌", font=("Helvetica", 8),
            bg="#f1f5f9", fg=self.text_secondary, relief="flat", bd=0, cursor="hand2",
            padx=3, pady=0, command=self._toggle_pin
        )
        self.btn_pin.pack(side=tk.RIGHT, padx=(0, 3))

        # 5 个紧凑精致操作按钮
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
        """绑定点击事件：点击小猫咪图标立即弹出操作页面"""
        self.icon_frame.bind("<Button-1>", lambda e: self._switch_to_card_state())
        self.lbl_cute_icon.bind("<Button-1>", lambda e: self._switch_to_card_state())

        self.dot_frame.bind("<Button-1>", lambda e: self._switch_to_card_state())

    def _global_mouse_watcher(self):
        """
        高频全局物理鼠标位置探针（40ms 轮询）
        - 状态 1 (dot): 鼠标移动到边缘微点附近 ➔ 浮现 🐱 小图标
        - 状态 2 (icon): 鼠标停留在图标上等待点击；鼠标移开 400ms ➔ 自动缩回微点
        - 状态 3 (card): 展开的操作页面；鼠标移开 450ms (且未钉住) ➔ 缩回微点
        """
        try:
            mx = self.root.winfo_pointerx()
            my = self.root.winfo_pointery()

            wx = self.root.winfo_rootx()
            wy = self.root.winfo_rooty()
            ww = self.root.winfo_width()
            wh = self.root.winfo_height()

            if self.current_state == "dot":
                # 鼠标靠近屏幕最右侧且在 Y 轴中心区域 -> 浮现 🐱 小图标
                in_edge_trigger = (mx >= self.screen_width - 24) and (abs(my - self.center_y) <= 50)
                if in_edge_trigger:
                    self._outside_count = 0
                    self._switch_to_icon_state()

            elif self.current_state == "icon":
                # 鼠标在 🐱 小图标范围内
                is_inside = (wx - 4 <= mx <= wx + ww + 6) and (wy - 4 <= my <= wy + wh + 4)
                if is_inside:
                    self._outside_count = 0
                else:
                    self._outside_count += 1
                    # 鼠标移出图标超过 400ms 自动缩回微点
                    if self._outside_count >= 10:
                        self._outside_count = 0
                        self._switch_to_dot_state()

            elif self.current_state == "card":
                # 鼠标在操作卡片范围内
                if not self.is_pinned:
                    is_inside = (wx - 4 <= mx <= wx + ww + 6) and (wy - 4 <= my <= wy + wh + 4)
                    if is_inside:
                        self._outside_count = 0
                    else:
                        self._outside_count += 1
                        # 鼠标移出卡片超过 450ms 自动缩回微点
                        if self._outside_count >= 11:
                            self._outside_count = 0
                            self._switch_to_dot_state()
        except Exception:
            pass

        self.root.after(40, self._global_mouse_watcher)

    def _switch_to_dot_state(self):
        """形态 1：切换为极小微点 (8x32)"""
        self.current_state = "dot"
        self.is_pinned = False
        self.card_frame.pack_forget()
        self.icon_frame.pack_forget()
        self.dot_frame.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.DOT_WIDTH
        y = self.dot_y
        self.root.geometry(f"{self.DOT_WIDTH}x{self.DOT_HEIGHT}+{x}+{y}")
        self.root.lift()
        self._set_macos_system_topmost()

    def _switch_to_icon_state(self):
        """形态 2：浮现 🐱 萌猫小图标 (40x40)"""
        self.current_state = "icon"
        self.dot_frame.pack_forget()
        self.card_frame.pack_forget()
        self.icon_frame.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.ICON_SIZE
        y = self.icon_y
        self.root.geometry(f"{self.ICON_SIZE}x{self.ICON_SIZE}+{x}+{y}")
        self.root.lift()
        self._set_macos_system_topmost()

    def _switch_to_card_state(self):
        """形态 3：点击后弹出完整操作卡片 (195x285)"""
        self.current_state = "card"
        self.dot_frame.pack_forget()
        self.icon_frame.pack_forget()
        self.card_frame.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.CARD_WIDTH
        y = self.card_y
        self.root.geometry(f"{self.CARD_WIDTH}x{self.CARD_HEIGHT}+{x}+{y}")
        self.root.lift()
        self._set_macos_system_topmost()

    def _toggle_pin(self):
        """切换钉住锁定"""
        self.is_pinned = not self.is_pinned
        if self.is_pinned:
            self.btn_pin.configure(bg="#6366f1", fg="#ffffff", text="📌")
        else:
            self.btn_pin.configure(bg="#f1f5f9", fg=self.text_secondary, text="📌")

    def collapse_immediate(self):
        """立即缩回微点"""
        self._switch_to_dot_state()

    def _set_macos_system_topmost(self):
        """利用 macOS AppKit 原生接口将悬浮窗提升为全局系统级悬浮 (跨所有第三方应用与全屏桌面均保持可见)"""
        if sys.platform != "darwin":
            return
        try:
            import AppKit
            self.root.update_idletasks()

            for win in AppKit.NSApp.windows():
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
        self._switch_to_dot_state()

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
