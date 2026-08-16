"""
桌面边缘吸附快捷唤醒小程序 (Edge 3-Tier Cute Floating Dock - 1:1 像素级方案一还原版)
- 默认隐藏状态 (Tier 1)：屏幕右侧边缘仅露出方案图同款 3D 萌萌蓬松小猫爪 (🐾 粉嫩肉垫)，无任何方框底色，零视觉负担；
- 鼠标滑过状态 (Tier 2)：小猫探出头，平滑滑出 3D 纯圆发光萌猫水晶球 (🐱 方案图同款发光球)；
- 点击展开状态 (Tier 3)：点击展开 1:1 还原的高颜值磨砂卡片，包含 5 大精美彩色胶囊药丸按钮；
- 全局 30ms 硬件鼠标探针 + macOS AppKit 系统级全局置顶。
"""
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable
from PIL import Image, ImageDraw, ImageFilter, ImageTk

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.browser_manager import BrowserManager


class FloatingDock:
    """
    1:1 像素级还原方案效果图的萌猫悬浮岛
    """

    PAW_WIDTH = 46
    PAW_HEIGHT = 54

    BUBBLE_SIZE = 56

    CARD_WIDTH = 215
    CARD_HEIGHT = 310

    def __init__(self, master=None, main_app=None, browser_mgr: Optional[BrowserManager] = None):
        self.main_app = main_app
        self.browser_mgr = browser_mgr or (main_app.browser_mgr if main_app else BrowserManager())
        self.is_standalone = master is None

        if self.is_standalone:
            self.root = tk.Tk()
        else:
            self.root = tk.Toplevel(master)

        # 窗口基础属性：无边框、全局置顶、系统级透明背景
        self.root.overrideredirect(True)
        try:
            self.root.attributes("-topmost", True)
        except Exception:
            pass

        # 启用 macOS 真正的窗口透明通道 (消除一切方框白底)
        if sys.platform == "darwin":
            try:
                self.root.config(bg="systemTransparent")
            except Exception:
                self.root.config(bg="#f8fafc")
        else:
            self.root.config(bg="#f8fafc")

        # 状态变量: 'paw' | 'bubble' | 'card'
        self.current_state = "paw"
        self.is_pinned = False
        self._outside_count = 0

        # 屏幕几何计算
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.center_y = max(120, int(self.screen_height / 2))

        # 各形态 Y 坐标
        self.paw_y = self.center_y - self.PAW_HEIGHT // 2
        self.bubble_y = self.center_y - self.BUBBLE_SIZE // 2
        self.card_y = self.center_y - self.CARD_HEIGHT // 2

        # 载入与预渲染 1:1 高清透明资产
        self._load_or_generate_assets()

        self._build_ui()
        self._bind_events()

        # 默认形态：🐾 探出 3D 小猫爪
        self._switch_to_paw_state()

        # 核心 1：启动 30ms 全局硬件鼠标探针 (跨应用秒级感应)
        self.root.after(80, self._global_mouse_watcher)

        # 核心 2：配置 macOS 原生系统级全局置顶（跨所有第三方应用/全屏桌面常驻可见）
        self.root.after(150, self._set_macos_system_topmost)
        self.root.after(2500, self._maintain_macos_topmost)

        # 启动后检测一次浏览器状态
        self.root.after(500, self._check_browser_status_async)

    def _load_or_generate_assets(self):
        """载入方案同款高清透明素材，若不存在则使用高保真 PIL 渲染"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        mockup_paw_path = os.path.join(current_dir, "mockup_paw_exact.png")
        mockup_orb_path = os.path.join(current_dir, "mockup_orb_exact.png")

        # 1. 3D 蓬松小猫爪素材
        if os.path.exists(mockup_paw_path):
            img_paw = Image.open(mockup_paw_path).convert("RGBA")
            img_paw = img_paw.resize((self.PAW_WIDTH, self.PAW_HEIGHT), Image.Resampling.LANCZOS)
            self.photo_paw = ImageTk.PhotoImage(img_paw)
        else:
            self.photo_paw = self._render_fallback_paw()

        # 2. 3D 萌猫发光水晶球素材
        if os.path.exists(mockup_orb_path):
            img_orb = Image.open(mockup_orb_path).convert("RGBA")
            img_orb = img_orb.resize((self.BUBBLE_SIZE, self.BUBBLE_SIZE), Image.Resampling.LANCZOS)
            self.photo_orb = ImageTk.PhotoImage(img_orb)
        else:
            self.photo_orb = self._render_fallback_orb()

    def _render_fallback_paw(self):
        """高质量备用 3D 猫爪渲染"""
        w, h = self.PAW_WIDTH * 3, self.PAW_HEIGHT * 3
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([w // 3, h // 6, w + w // 3, h * 5 // 6], fill="#faf8f5")
        d.rectangle([w * 2 // 3, h // 4, w, h * 3 // 4], fill="#f5f0e8")
        d.ellipse([w * 0.42, h * 0.38, w * 0.75, h * 0.68], fill="#fb7185", outline="#fda4af", width=3)
        for tx, ty in [(0.32, 0.16), (0.16, 0.30), (0.16, 0.52), (0.32, 0.66)]:
            d.ellipse([w * tx, h * ty, w * (tx + 0.2), h * (ty + 0.18)], fill="#fb7185", outline="#fda4af", width=3)
        img = img.resize((self.PAW_WIDTH, self.PAW_HEIGHT), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _render_fallback_orb(self):
        """高质量备用 3D 水晶球渲染"""
        s = self.BUBBLE_SIZE * 3
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([6, 6, s - 6, s - 6], fill="#8b5cf6", outline="#c084fc", width=6)
        img = img.resize((self.BUBBLE_SIZE, self.BUBBLE_SIZE), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(img)

    def _build_ui(self):
        """构建三级视图容器"""
        trans_bg = "systemTransparent" if sys.platform == "darwin" else "#f8fafc"

        # ═══════════════════════════════════════════════════════════
        # 视图 1：3D 蓬松探出小猫爪 Canvas (46 x 54)
        # ═══════════════════════════════════════════════════════════
        self.paw_canvas = tk.Canvas(
            self.root,
            width=self.PAW_WIDTH,
            height=self.PAW_HEIGHT,
            bg=trans_bg,
            highlightthickness=0,
            cursor="hand2"
        )
        self.paw_canvas.create_image(
            self.PAW_WIDTH // 2, self.PAW_HEIGHT // 2, image=self.photo_paw
        )

        # ═══════════════════════════════════════════════════════════
        # 视图 2：3D 纯圆发光萌猫水晶球 Canvas (56 x 56)
        # ═══════════════════════════════════════════════════════════
        self.bubble_canvas = tk.Canvas(
            self.root,
            width=self.BUBBLE_SIZE,
            height=self.BUBBLE_SIZE,
            bg=trans_bg,
            highlightthickness=0,
            cursor="hand2"
        )
        self.bubble_canvas.create_image(
            self.BUBBLE_SIZE // 2, self.BUBBLE_SIZE // 2, image=self.photo_orb
        )

        # ═══════════════════════════════════════════════════════════
        # 视图 3：1:1 还原方案效果图的磨砂操作卡片 (215 x 310)
        # ═══════════════════════════════════════════════════════════
        self.card_frame = tk.Frame(
            self.root,
            bg="#ffffff",
            highlightbackground="#c084fc",
            highlightthickness=2,
            bd=0,
            padx=10,
            pady=8
        )

        # 顶部标题栏：萌猫头像 + 状态圆点 + 标题 + 📌 钉住 + ✕
        header_row = tk.Frame(self.card_frame, bg="#ffffff")
        header_row.pack(fill=tk.X, pady=(0, 6))

        # 小猫头像微缩
        lbl_avatar = tk.Label(header_row, text="🐱", font=("Helvetica", 14), bg="#f3e8ff", fg="#7c3aed", padx=4, pady=2)
        lbl_avatar.pack(side=tk.LEFT, padx=(0, 4))

        title_box = tk.Frame(header_row, bg="#ffffff")
        title_box.pack(side=tk.LEFT)

        title_lbl = tk.Label(title_box, text="Miaoshou Assistant", font=("Helvetica", 9, "bold"),
                             bg="#ffffff", fg="#0f172a")
        title_lbl.pack(anchor="w")

        status_sub = tk.Frame(title_box, bg="#ffffff")
        status_sub.pack(anchor="w")

        self.status_dot = tk.Label(status_sub, text="●", font=("Helvetica", 8), bg="#ffffff", fg="#16a34a")
        self.status_dot.pack(side=tk.LEFT, padx=(0, 2))

        self.status_txt = tk.Label(status_sub, text="Online", font=("Helvetica", 8), bg="#ffffff", fg="#64748b")
        self.status_txt.pack(side=tk.LEFT)

        btn_hide = tk.Button(
            header_row, text="✕", font=("Helvetica", 8, "bold"),
            bg="#f1f5f9", fg="#64748b", relief="flat", bd=0, cursor="hand2",
            padx=4, pady=0, command=self._switch_to_paw_state
        )
        btn_hide.pack(side=tk.RIGHT)

        self.btn_pin = tk.Button(
            header_row, text="📌", font=("Helvetica", 8),
            bg="#f1f5f9", fg="#64748b", relief="flat", bd=0, cursor="hand2",
            padx=4, pady=0, command=self._toggle_pin
        )
        self.btn_pin.pack(side=tk.RIGHT, padx=(0, 3))

        # 5 大精美彩色胶囊药丸按钮（1:1 匹配效果图）
        btn_configs = [
            ("🔍  1688 货源直达", "#f97316", "#ffffff", self._on_btn_1688),
            ("📸  1688 素材采集", "#f43f5e", "#ffffff", self._on_btn_preview_1688),
            ("📊  SKU 智能核算", "#22c55e", "#ffffff", self._on_btn_calcfee),
            ("🔑  妙手免密直达", "#3b82f6", "#ffffff", self._on_btn_miaoshou),
            ("📦  一键批量录入", "#a855f7", "#ffffff", self._on_btn_auto_execute),
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
                pady=5,
                anchor="w",
                padx=10,
                command=cmd
            )
            btn.pack(fill=tk.X, pady=3)

        # 底部展开主窗口药丸按钮
        btn_show_main = tk.Button(
            self.card_frame,
            text="🖥️  展开完整控制台",
            font=("Helvetica", 8, "bold"),
            bg="#f1f5f9",
            fg="#475569",
            activebackground="#e2e8f0",
            relief="flat",
            bd=0,
            cursor="hand2",
            pady=4,
            command=self._on_show_main_window
        )
        btn_show_main.pack(fill=tk.X, pady=(4, 0))

        # ═══════════════════════════════════════════════════════════
        # 4. 右键快捷弹出菜单 (Context Menu)
        # ═══════════════════════════════════════════════════════════
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="🖥️ 展开主控制台", command=self._on_show_main_window)
        self.context_menu.add_command(label="🔄 刷新浏览器状态", command=self._check_browser_status_async)
        self.context_menu.add_command(label="📌 切换钉住模式", command=self._toggle_pin)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✕ 收回为小猫爪", command=self._switch_to_paw_state)

    def _bind_events(self):
        """绑定点击、右键与 Esc 键退出事件"""
        self.paw_canvas.bind("<Button-1>", lambda e: self._switch_to_card_state())
        self.bubble_canvas.bind("<Button-1>", lambda e: self._switch_to_card_state())

        self.paw_canvas.bind("<Button-2>", self._show_context_menu)
        self.paw_canvas.bind("<Button-3>", self._show_context_menu)
        self.bubble_canvas.bind("<Button-2>", self._show_context_menu)
        self.bubble_canvas.bind("<Button-3>", self._show_context_menu)
        self.card_frame.bind("<Button-2>", self._show_context_menu)
        self.card_frame.bind("<Button-3>", self._show_context_menu)

        self.root.bind("<Escape>", lambda e: self._switch_to_paw_state())

    def _show_context_menu(self, event):
        """弹出右键菜单"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _global_mouse_watcher(self):
        """
        高频全局物理鼠标探针（30ms 轮询）
        跨应用 100% 灵敏响应滑入滑出
        """
        try:
            mx = self.root.winfo_pointerx()
            my = self.root.winfo_pointery()

            wx = self.root.winfo_rootx()
            wy = self.root.winfo_rooty()
            ww = self.root.winfo_width()
            wh = self.root.winfo_height()

            if self.current_state == "paw":
                # 鼠标靠近屏幕最右侧边缘 (40px 范围) ➔ 平滑滑出 🐱 水晶球
                in_edge_trigger = (mx >= self.screen_width - 45) and (abs(my - self.center_y) <= 60)
                if in_edge_trigger:
                    self._outside_count = 0
                    self._switch_to_bubble_state()

            elif self.current_state == "bubble":
                # 鼠标在 🐱 水晶球范围内
                is_inside = (wx - 8 <= mx <= wx + ww + 10) and (wy - 8 <= my <= wy + wh + 8)
                if is_inside:
                    self._outside_count = 0
                else:
                    self._outside_count += 1
                    # 离开水晶球 350ms 自动缩回 🐾 小猫爪
                    if self._outside_count >= 11:
                        self._outside_count = 0
                        self._switch_to_paw_state()

            elif self.current_state == "card":
                # 鼠标在操作卡片范围内
                if not self.is_pinned:
                    is_inside = (wx - 8 <= mx <= wx + ww + 10) and (wy - 8 <= my <= wy + wh + 8)
                    if is_inside:
                        self._outside_count = 0
                    else:
                        self._outside_count += 1
                        # 离开卡片 450ms 自动缩回 🐾 小猫爪
                        if self._outside_count >= 14:
                            self._outside_count = 0
                            self._switch_to_paw_state()
        except Exception:
            pass

        self.root.after(30, self._global_mouse_watcher)

    def _switch_to_paw_state(self):
        """形态 1：切换为 🐾 3D 蓬松探出小猫爪 (46 x 54)"""
        self.current_state = "paw"
        self.is_pinned = False
        self.card_frame.pack_forget()
        self.bubble_canvas.pack_forget()
        self.paw_canvas.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.PAW_WIDTH
        y = self.paw_y
        self.root.geometry(f"{self.PAW_WIDTH}x{self.PAW_HEIGHT}+{x}+{y}")
        self.root.lift()
        self._set_macos_system_topmost()

    def _switch_to_bubble_state(self):
        """形态 2：丝滑滑出 🐱 3D 纯圆水晶球 (56 x 56)"""
        self.current_state = "bubble"
        self.paw_canvas.pack_forget()
        self.card_frame.pack_forget()
        self.bubble_canvas.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.BUBBLE_SIZE
        y = self.bubble_y
        self.root.geometry(f"{self.BUBBLE_SIZE}x{self.BUBBLE_SIZE}+{x}+{y}")
        self.root.lift()
        self._set_macos_system_topmost()

    def _switch_to_card_state(self):
        """形态 3：点击后展开 1:1 磨砂操作卡片 (215 x 310)"""
        self.current_state = "card"
        self.paw_canvas.pack_forget()
        self.bubble_canvas.pack_forget()
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
            self.btn_pin.configure(bg="#f1f5f9", fg="#64748b", text="📌")

    def collapse_immediate(self):
        """立即缩回小猫爪"""
        self._switch_to_paw_state()

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
                    self.status_txt.configure(text="Online")
                else:
                    self.status_dot.configure(fg="#dc2626")
                    self.status_txt.configure(text="Offline")
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
        self._switch_to_paw_state()

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
