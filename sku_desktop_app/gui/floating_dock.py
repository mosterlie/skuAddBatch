"""
桌面边缘吸附快捷唤醒小程序 (Edge 3-Tier Cute Floating Dock - 方案一：🐾 探出小猫爪版)
- 默认隐藏状态 (Tier 1)：屏幕右侧边缘仅露出一只 24x28 像素的小萌猫爪 (🐾)，半掩在边框后，零视觉负担；
- 鼠标滑过状态 (Tier 2)：小猫探出头，瞬间滑出 50x50 纯圆透明萌猫水晶球 (🐱 带呼吸光圈与微反光)；
- 点击展开状态 (Tier 3)：点击 🐱 水晶球，弹出 16px 圆角高颜值快捷操作工作台卡片；
- 鼠标移开优雅收起为 🐾 猫爪，支持 📌 钉住锁定、右键快捷菜单、Esc 一键收回与全局跨应用置顶。
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
    三级渐进式边缘悬浮小窗（🐾 探出小猫爪 ➔ 🐱 萌猫水晶球 ➔ 展开操作面板）
    """

    PAW_WIDTH = 24
    PAW_HEIGHT = 28

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

        # 启用 macOS 真正的窗口透明通道
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

        # 预渲染高质量抗锯齿透明资产
        self._generate_canvas_assets()

        self._build_ui()
        self._bind_events()

        # 默认形态：🐾 探出小猫爪
        self._switch_to_paw_state()

        # 核心 1：启动 30ms 全局硬件鼠标探针 (跨应用秒级感应)
        self.root.after(80, self._global_mouse_watcher)

        # 核心 2：配置 macOS 原生系统级全局置顶（跨所有第三方应用/全屏桌面常驻可见）
        self.root.after(150, self._set_macos_system_topmost)
        self.root.after(2500, self._maintain_macos_topmost)

        # 启动后检测一次浏览器状态
        self.root.after(500, self._check_browser_status_async)

    def _generate_canvas_assets(self):
        """利用 PIL 超采样预渲染像素级平滑透明图形"""
        scale = 3

        # 1. 探出小猫爪底座背景 (24 x 28) - 左侧圆弧，右侧贴边
        pw, ph = self.PAW_WIDTH * scale, self.PAW_HEIGHT * scale
        img_paw = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        d_paw = ImageDraw.Draw(img_paw)
        r_paw = ph // 2
        d_paw.rounded_rectangle([0, 0, pw * 2, ph], radius=r_paw, fill="#818cf8", outline="#c7d2fe", width=scale)
        img_paw = img_paw.resize((self.PAW_WIDTH, self.PAW_HEIGHT), Image.Resampling.LANCZOS)
        self.photo_paw_bg = ImageTk.PhotoImage(img_paw)

        # 2. 萌宠圆形水晶球 (50 x 50) - 默认与悬停两套质感
        def _make_bubble(bg_c="#6366f1", border_c="#c7d2fe"):
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
        # 视图 1：🐾 探出小猫爪 Canvas (24 x 28)
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
            self.PAW_WIDTH // 2, self.PAW_HEIGHT // 2, image=self.photo_paw_bg
        )
        # 居中小猫爪 emoji
        self.paw_canvas.create_text(
            self.PAW_WIDTH // 2 - 1,
            self.PAW_HEIGHT // 2,
            text="🐾",
            font=("Helvetica", 14)
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
            padx=4, pady=0, command=self._switch_to_paw_state
        )
        btn_hide.pack(side=tk.RIGHT)

        self.btn_pin = tk.Button(
            header_row, text="📌", font=("Helvetica", 8),
            bg="#f1f5f9", fg="#64748b", relief="flat", bd=0, cursor="hand2",
            padx=4, pady=0, command=self._toggle_pin
        )
        self.btn_pin.pack(side=tk.RIGHT, padx=(0, 3))

        # 5 个高颜值高频操作胶囊按钮
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
        # 点击猫爪或水晶球直接展开卡片
        self.paw_canvas.bind("<Button-1>", lambda e: self._switch_to_card_state())
        self.bubble_canvas.bind("<Button-1>", lambda e: self._switch_to_card_state())

        # 右键点击弹出快捷菜单 (macOS <Button-2> / <Button-3>)
        self.paw_canvas.bind("<Button-2>", self._show_context_menu)
        self.paw_canvas.bind("<Button-3>", self._show_context_menu)
        self.bubble_canvas.bind("<Button-2>", self._show_context_menu)
        self.bubble_canvas.bind("<Button-3>", self._show_context_menu)
        self.card_frame.bind("<Button-2>", self._show_context_menu)
        self.card_frame.bind("<Button-3>", self._show_context_menu)

        # 全局 Esc 键快速收缩
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
                # 鼠标靠近屏幕最右侧边缘 (30px 范围) ➔ 平滑滑出 🐱 水晶球
                in_edge_trigger = (mx >= self.screen_width - 32) and (abs(my - self.center_y) <= 50)
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
                    # 离开水晶球 350ms 自动缩回 🐾 小猫爪
                    if self._outside_count >= 11:
                        self._outside_count = 0
                        self._switch_to_paw_state()

            elif self.current_state == "card":
                # 鼠标在操作卡片范围内
                if not self.is_pinned:
                    is_inside = (wx - 6 <= mx <= wx + ww + 8) and (wy - 6 <= my <= wy + wh + 6)
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
        """形态 1：切换为 🐾 探出小猫爪 (24 x 28)"""
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
        """形态 2：丝滑滑出 🐱 纯圆水晶球 (50 x 50)"""
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
        """形态 3：点击后展开完整操作卡片 (205 x 295)"""
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
