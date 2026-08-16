"""
桌面边缘吸附快捷唤醒小程序 (Edge 3-Tier Cute Floating Dock - Apple/Glassmorphism 极致美化版)
- 默认状态 (Tier 1)：屏幕边缘仅显示 10x50 像素的超微型荧光胶囊切片，完全透明无方框，零视觉遮挡；
- 鼠标滑过 (Tier 2)：平滑滑出 50x50 圆形萌宠悬浮球 (🐱 萌猫水晶球，纯圆无方框背景，带呼吸光圈)；
- 点击图标 (Tier 3)：点击 🐱 猫咪水晶球，平滑展开超紧凑现代快捷操作卡片；
- 鼠标离开 (Tier 1 收缩)：未钉住时自动丝滑收回微型光条，支持 📌 钉住锁定与全局 macOS 跨应用置顶。
"""
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Optional, Callable
from PIL import Image, ImageDraw, ImageTk

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.browser_manager import BrowserManager


class FloatingDock:
    """
    三级渐进式边缘悬浮小窗（纯圆透明萌宠水晶球 + 丝滑展开动效 + 系统级跨应用常驻）
    """

    DOT_WIDTH = 10
    DOT_HEIGHT = 48

    BUBBLE_SIZE = 50

    CARD_WIDTH = 205
    CARD_HEIGHT = 295

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

        # 启用 macOS 真正的窗口透明通道 (消除所有四角方框)
        if sys.platform == "darwin":
            try:
                self.root.config(bg="systemTransparent")
            except Exception:
                self.root.config(bg="#f8fafc")
        else:
            self.root.config(bg="#f8fafc")

        # 状态变量: 'dot' | 'bubble' | 'card'
        self.current_state = "dot"
        self.is_pinned = False
        self._outside_count = 0
        self._animating = False

        # 屏幕尺寸计算
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self.center_y = max(120, int(self.screen_height / 2))

        # 各形态 Y 坐标
        self.dot_y = self.center_y - self.DOT_HEIGHT // 2
        self.bubble_y = self.center_y - self.BUBBLE_SIZE // 2
        self.card_y = self.center_y - self.CARD_HEIGHT // 2

        # 预渲染高质量抗锯齿透明资产
        self._generate_canvas_assets()

        self._build_ui()
        self._bind_events()

        # 默认形态：极小边缘微光胶囊
        self._switch_to_dot_state()

        # 核心 1：启动 35ms 全局硬件鼠标探针 (跨应用秒级感应)
        self.root.after(80, self._global_mouse_watcher)

        # 核心 2：配置 macOS 原生系统级全局置顶（跨所有应用/全屏桌面保持可见）
        self.root.after(150, self._set_macos_system_topmost)
        self.root.after(2500, self._maintain_macos_topmost)

        # 启动后检测一次浏览器状态
        self.root.after(500, self._check_browser_status_async)

    def _generate_canvas_assets(self):
        """利用 PIL 超采样预渲染像素级平滑透明图形"""
        # 1. 边缘微光胶囊 (10 x 48)
        scale = 3
        sw, sh = self.DOT_WIDTH * scale, self.DOT_HEIGHT * scale
        img_dot = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        d_dot = ImageDraw.Draw(img_dot)
        # 左侧圆角胶囊
        d_dot.rounded_rectangle([0, 0, sw * 2, sh], radius=sw, fill="#6366f1")
        # 内部亮光指示条
        d_dot.line([sw // 2, sh // 4, sw // 2, sh * 3 // 4], fill="#c7d2fe", width=2 * scale)
        img_dot = img_dot.resize((self.DOT_WIDTH, self.DOT_HEIGHT), Image.Resampling.LANCZOS)
        self.photo_dot = ImageTk.PhotoImage(img_dot)

        # 2. 萌宠圆形水晶球 (50 x 50) - 默认与悬停两套质感
        def _make_bubble(bg_c="#6366f1", border_c="#c7d2fe", inner_c="#818cf8"):
            s = self.BUBBLE_SIZE * scale
            img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            # 主圆形外圈
            d.ellipse([3 * scale, 3 * scale, s - 3 * scale, s - 3 * scale], fill=bg_c, outline=border_c, width=2 * scale)
            # 顶部微反光弧光
            d.arc([8 * scale, 6 * scale, s - 8 * scale, s // 2], start=200, end=340, fill="#ffffff", width=2 * scale)
            img = img.resize((self.BUBBLE_SIZE, self.BUBBLE_SIZE), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)

        self.photo_bubble_normal = _make_bubble("#6366f1", "#c7d2fe")
        self.photo_bubble_hover = _make_bubble("#4f46e5", "#ffffff")

    def _build_ui(self):
        """构建三级视图容器"""
        trans_bg = "systemTransparent" if sys.platform == "darwin" else "#f8fafc"

        # ═══════════════════════════════════════════════════════════
        # 视图 1：极小边缘微光胶囊 Canvas (10 x 48)
        # ═══════════════════════════════════════════════════════════
        self.dot_canvas = tk.Canvas(
            self.root,
            width=self.DOT_WIDTH,
            height=self.DOT_HEIGHT,
            bg=trans_bg,
            highlightthickness=0,
            cursor="hand2"
        )
        self.dot_canvas_img = self.dot_canvas.create_image(
            self.DOT_WIDTH // 2, self.DOT_HEIGHT // 2, image=self.photo_dot
        )

        # ═══════════════════════════════════════════════════════════
        # 视图 2：纯圆萌宠悬浮水晶球 Canvas (50 x 50)
        # ═══════════════════════════════════════════════════════════
        self.bubble_canvas = tk.Canvas(
            self.root,
            width=self.BUBBLE_SIZE,
            height=self.BUBBLE_SIZE,
            bg=trans_bg,
            highlightthickness=0,
            cursor="hand2"
        )
        self.bubble_bg_item = self.bubble_canvas.create_image(
            self.BUBBLE_SIZE // 2, self.BUBBLE_SIZE // 2, image=self.photo_bubble_normal
        )
        # 居中萌猫表情
        self.bubble_text_item = self.bubble_canvas.create_text(
            self.BUBBLE_SIZE // 2,
            self.BUBBLE_SIZE // 2 - 1,
            text="🐱",
            font=("Helvetica", 22)
        )

        # ═══════════════════════════════════════════════════════════
        # 视图 3：点击后展开的操作页面卡片 (205 x 295)
        # ═══════════════════════════════════════════════════════════
        self.card_frame = tk.Frame(
            self.root,
            bg="#ffffff",
            highlightbackground="#818cf8",
            highlightthickness=1,
            bd=0,
            padx=8,
            pady=7
        )

        # 顶部标题栏：萌猫标题 + 状态小圆点 + 📌 钉住 + ✕
        header_row = tk.Frame(self.card_frame, bg="#ffffff")
        header_row.pack(fill=tk.X, pady=(0, 4))

        self.status_dot = tk.Label(header_row, text="●", font=("Helvetica", 10), bg="#ffffff", fg="#dc2626")
        self.status_dot.pack(side=tk.LEFT, padx=(0, 3))

        title_lbl = tk.Label(header_row, text="妙手萌盒 🐱", font=("Helvetica", 9, "bold"),
                             bg="#ffffff", fg="#0f172a")
        title_lbl.pack(side=tk.LEFT)

        btn_hide = tk.Button(
            header_row, text="✕", font=("Helvetica", 8, "bold"),
            bg="#f1f5f9", fg="#64748b", relief="flat", bd=0, cursor="hand2",
            padx=4, pady=0, command=self._switch_to_dot_state
        )
        btn_hide.pack(side=tk.RIGHT)

        self.btn_pin = tk.Button(
            header_row, text="📌", font=("Helvetica", 8),
            bg="#f1f5f9", fg="#64748b", relief="flat", bd=0, cursor="hand2",
            padx=4, pady=0, command=self._toggle_pin
        )
        self.btn_pin.pack(side=tk.RIGHT, padx=(0, 3))

        # 5 个高颜值高频操作按钮
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
        """绑定点击事件：点击小猫咪水晶球立即弹出操作页面"""
        # 点击猫咪水晶球展开卡片
        self.bubble_canvas.bind("<Button-1>", lambda e: self._switch_to_card_state())
        self.dot_canvas.bind("<Button-1>", lambda e: self._switch_to_card_state())

    def _global_mouse_watcher(self):
        """
        高频全局物理鼠标探针（35ms 轮询）
        跨应用 100% 灵敏响应滑入滑出
        """
        try:
            mx = self.root.winfo_pointerx()
            my = self.root.winfo_pointery()

            wx = self.root.winfo_rootx()
            wy = self.root.winfo_rooty()
            ww = self.root.winfo_width()
            wh = self.root.winfo_height()

            if self.current_state == "dot":
                # 鼠标靠近屏幕最右侧边缘 (24px 范围) ➔ 平滑滑出 🐱 水晶球
                in_edge_trigger = (mx >= self.screen_width - 24) and (abs(my - self.center_y) <= 55)
                if in_edge_trigger:
                    self._outside_count = 0
                    self._switch_to_bubble_state()

            elif self.current_state == "bubble":
                # 鼠标在 🐱 水晶球范围内
                is_inside = (wx - 6 <= mx <= wx + ww + 8) and (wy - 6 <= my <= wy + wh + 6)
                if is_inside:
                    self._outside_count = 0
                    self.bubble_canvas.itemconfig(self.bubble_bg_item, image=self.photo_bubble_hover)
                else:
                    self.bubble_canvas.itemconfig(self.bubble_bg_item, image=self.photo_bubble_normal)
                    self._outside_count += 1
                    # 离开水晶球 380ms 自动缩回微光胶囊
                    if self._outside_count >= 11:
                        self._outside_count = 0
                        self._switch_to_dot_state()

            elif self.current_state == "card":
                # 鼠标在操作卡片范围内
                if not self.is_pinned:
                    is_inside = (wx - 6 <= mx <= wx + ww + 8) and (wy - 6 <= my <= wy + wh + 6)
                    if is_inside:
                        self._outside_count = 0
                    else:
                        self._outside_count += 1
                        # 离开卡片 450ms 自动缩回微点
                        if self._outside_count >= 13:
                            self._outside_count = 0
                            self._switch_to_dot_state()
        except Exception:
            pass

        self.root.after(35, self._global_mouse_watcher)

    def _switch_to_dot_state(self):
        """形态 1：切换为极小微光胶囊 (10 x 48)"""
        self.current_state = "dot"
        self.is_pinned = False
        self.card_frame.pack_forget()
        self.bubble_canvas.pack_forget()
        self.dot_canvas.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.DOT_WIDTH
        y = self.dot_y
        self.root.geometry(f"{self.DOT_WIDTH}x{self.DOT_HEIGHT}+{x}+{y}")
        self.root.lift()
        self._set_macos_system_topmost()

    def _switch_to_bubble_state(self):
        """形态 2：丝滑滑出 🐱 纯圆水晶球 (50 x 50)"""
        self.current_state = "bubble"
        self.dot_canvas.pack_forget()
        self.card_frame.pack_forget()
        self.bubble_canvas.pack(fill=tk.BOTH, expand=True)

        x = self.screen_width - self.BUBBLE_SIZE
        y = self.bubble_y
        self.root.geometry(f"{self.BUBBLE_SIZE}x{self.BUBBLE_SIZE}+{x}+{y}")
        self.root.lift()
        self._set_macos_system_topmost()

    def _switch_to_card_state(self):
        """形态 3：点击后展开完整操作卡片 (205 x 295)"""
        self.current_state = "card"
        self.dot_canvas.pack_forget()
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
