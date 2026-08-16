"""
妙手 SKU 批量自动化录入助手 - 桌面 GUI 主界面
"""
import os
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.parser import SkuParser, SkuDataBundle
from core.browser_manager import BrowserManager, TabInfo
from core.executor import SkuExecutor
from core.scraper_1688 import Scraper1688
from core.login_helper import MiaoshouLoginHelper, load_saved_credentials, save_credentials
from core.plugin_server import PluginServerManager
from core.plugin_overlay_injector import inject_plugin_ui_into_1688_page
from gui.preview_1688_dialog import Preview1688Dialog
from gui.floating_dock import FloatingDock


class SkuAppGUI:
    """主桌面 GUI 应用程序"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("跨境电商智能工作台 (1688采集 • 数据整理 • 妙手批量录入)")
        self.root.geometry("880x720")
        self.root.minsize(840, 620)

        # 核心控制器
        self.browser_mgr = BrowserManager()
        self.current_bundle: Optional[SkuDataBundle] = None
        self.current_executor: Optional[SkuExecutor] = None
        self.available_tabs: List[TabInfo] = []
        self.is_running = False
        self.floating_dock: Optional[FloatingDock] = None

        # 启动 1688 插件与 calcfee 本地专属守护服务 (端口 31416)，并注入回调
        PluginServerManager.start_server(
            self.browser_mgr,
            31416,
            on_scan_callback=self._on_plugin_scan_callback,
            on_export_callback=self._on_calcfee_export_callback
        )
        from core.plugin_server import PluginServerHandler
        PluginServerHandler.on_dock_cmd_callback = self._on_dock_cmd

        # 初始化样式与界面布局
        self._setup_styles()
        self._create_widgets()

        # 启动后自动检查一次浏览器状态与初始化边缘悬浮岛
        self.root.after(500, self._async_refresh_browser_status)
        self.root.after(1000, self._init_floating_dock)

    def _setup_styles(self):
        """配置现代化主题样式"""
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except Exception:
            pass

        # 基础配色
        self.bg_color = "#f8fafc"
        self.card_bg = "#ffffff"
        self.text_primary = "#1e293b"
        self.text_secondary = "#64748b"
        self.border_color = "#e2e8f0"
        self.accent_blue = "#2563eb"
        self.accent_green = "#059669"
        self.accent_red = "#dc2626"

        self.root.configure(bg=self.bg_color)

        style.configure("TFrame", background=self.bg_color)
        style.configure("Card.TFrame", background=self.card_bg, relief="solid", borderwidth=1)
        style.configure("TLabel", background=self.bg_color, foreground=self.text_primary, font=("Helvetica", 10))
        style.configure("Card.TLabel", background=self.card_bg, foreground=self.text_primary, font=("Helvetica", 10))
        style.configure("Header.TLabel", background=self.bg_color, foreground=self.text_primary, font=("Helvetica", 14, "bold"))
        style.configure("Section.TLabel", background=self.card_bg, foreground=self.text_primary, font=("Helvetica", 11, "bold"))

        style.configure("Primary.TButton", font=("Helvetica", 11, "bold"), background=self.accent_green, foreground=self.text_primary)
        style.configure("Action.TButton", font=("Helvetica", 10), background="#f1f5f9", foreground=self.text_primary)
        style.configure("Stop.TButton", font=("Helvetica", 10, "bold"), background=self.accent_red, foreground=self.text_primary)

        style.configure("Main.TNotebook", background=self.bg_color)
        style.configure("Main.TNotebook.Tab", font=("Helvetica", 10, "bold"), padding=[18, 6])

    def _create_widgets(self):
        """构建界面主要组件"""
        # 主容器
        main_container = ttk.Frame(self.root, padding="14 12 14 12")
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. 顶部标题与状态栏
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 8))

        title_label = ttk.Label(header_frame, text="🤖 妙手与1688 跨境电商智能工作台", style="Header.TLabel")
        title_label.pack(side=tk.LEFT)

        sub_label = ttk.Label(header_frame, text="商品采集 • 数据整理 • 批量录入一站式助手", font=("Helvetica", 9), foreground=self.text_secondary)
        sub_label.pack(side=tk.LEFT, padx=(10, 0), pady=(4, 0))

        # 快捷唤起边缘悬浮岛按钮
        btn_dock = tk.Button(
            header_frame,
            text="⚡ 唤起边缘悬浮岛",
            font=("Helvetica", 9, "bold"),
            bg="#6366f1",
            fg="#ffffff",
            activebackground="#4f46e5",
            activeforeground="#ffffff",
            highlightbackground="#6366f1",
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=3,
            command=self._on_toggle_floating_dock
        )
        btn_dock.pack(side=tk.RIGHT)

        # 2. 顶级主菜单现代分段导航栏 (Segmented Tab Bar)
        nav_container = tk.Frame(main_container, bg="#e2e8f0", padx=3, pady=3)
        nav_container.pack(fill=tk.X, pady=(0, 10))

        self.tab_buttons = []
        tab_defs = [
            ("📦 1. 商品采集 (1688素材)", 0),
            ("📊 2. 数据整理 (SKU核算)", 1),
            ("🚀 3. 妙手批量录入", 2)
        ]

        self.content_container = ttk.Frame(main_container, style="TFrame")
        self.content_container.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.tab_frames = []
        self.tab_collect = ttk.Frame(self.content_container, style="TFrame")
        self._build_collect_tab(self.tab_collect)
        self.tab_frames.append(self.tab_collect)

        self.tab_process = ttk.Frame(self.content_container, style="TFrame")
        self._build_process_tab(self.tab_process)
        self.tab_frames.append(self.tab_process)

        self.tab_entry = ttk.Frame(self.content_container, style="TFrame")
        self._build_entry_tab(self.tab_entry)
        self.tab_frames.append(self.tab_entry)

        self.active_tab_idx = 0
        for title, idx in tab_defs:
            btn = tk.Button(
                nav_container,
                text=title,
                font=("Helvetica", 10, "bold" if idx == 0 else "normal"),
                bg="#ffffff" if idx == 0 else "#e2e8f0",
                fg="#2563eb" if idx == 0 else "#64748b",
                activebackground="#ffffff",
                activeforeground="#2563eb",
                highlightbackground="#e2e8f0",
                relief="flat",
                bd=0,
                cursor="hand2",
                padx=14,
                pady=6,
                command=lambda i=idx: self._switch_tab(i)
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
            self.tab_buttons.append(btn)

        # 默认展示第 1 个 tab
        self._switch_tab(0)

        # 3. 底部常驻日志监控窗口
        self._create_log_console(main_container)

    def _switch_tab(self, idx: int):
        """切换主菜单页签"""
        self.active_tab_idx = idx
        for i, frame in enumerate(self.tab_frames):
            if i == idx:
                frame.pack(fill=tk.BOTH, expand=True)
            else:
                frame.pack_forget()

        for i, btn in enumerate(self.tab_buttons):
            if i == idx:
                btn.configure(
                    bg="#ffffff",
                    fg="#2563eb",
                    font=("Helvetica", 10, "bold"),
                    highlightbackground="#cbd5e1"
                )
            else:
                btn.configure(
                    bg="#e2e8f0",
                    fg="#64748b",
                    font=("Helvetica", 10),
                    highlightbackground="#e2e8f0"
                )

        if idx == 0:
            self._async_probe_1688_info()

    def _on_dock_cmd(self, action):
        """处理来自悬浮岛的 HTTP 接口命令，转发到 Tkinter 主线程"""
        if self.root:
            self.root.after(0, lambda: self._execute_dock_cmd(action))

    def _execute_dock_cmd(self, action):
        if action == '1688':
            self._on_open_1688()
        elif action == 'preview':
            self._on_download_1688()
        elif action == 'calc':
            self._on_open_sku_calc()
        elif action == 'miaoshou':
            self._on_launch_browser()
        elif action == 'batch':
            self._on_start_execution()
        elif action == 'main':
            try:
                if self.root.state() in ("iconic", "withdrawn"):
                    self.root.deiconify()
                    self.root.state("normal")
                self.root.lift()
                self.root.focus_force()
            except Exception:
                pass

    def _init_floating_dock(self):
        """初始化屏幕边缘吸附快捷悬浮岛"""
        if not self.floating_dock:
            try:
                self.floating_dock = FloatingDock(master=self.root, main_app=self, browser_mgr=self.browser_mgr)
            except Exception:
                pass

    def _on_toggle_floating_dock(self):
        """手动切换/呼出边缘快捷悬浮岛并最小化主窗口"""
        self._init_floating_dock()
        if self.floating_dock:
            self.floating_dock.show()
            self.root.iconify()
            self.append_log("⚡ 已唤出屏幕边缘快捷悬浮岛，鼠标移动到屏幕右侧把手即可唤醒快捷操作！", "info")

    def _build_collect_tab(self, parent):
        """构建【商品采集】菜单页面"""
        # 卡片 1: 平台直达与采集操作
        card_actions = ttk.Frame(parent, style="Card.TFrame", padding="16 14 16 14")
        card_actions.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(card_actions, text="🛒 1688 与妙手商品采集工作台", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 10))

        btn_row = ttk.Frame(card_actions, style="Card.TFrame")
        btn_row.pack(fill=tk.X, pady=(0, 12))

        # 按钮 1: 打开 1688
        btn_1688 = tk.Button(btn_row, text="🛒 1. 打开 1688", font=("Helvetica", 10, "bold"),
                             bg="#f97316", fg="#1e293b", activebackground="#ea580c", activeforeground="#1e293b",
                             highlightbackground="#f97316", relief="flat", cursor="hand2", padx=14, pady=8,
                             command=self._on_open_1688)
        btn_1688.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 8))

        # 按钮 2: 1688数据预览与采集
        btn_preview = tk.Button(btn_row, text="✨ 2. 1688数据预览与采集", font=("Helvetica", 10, "bold"),
                                bg="#ec4899", fg="#1e293b", activebackground="#db2777", activeforeground="#1e293b",
                                highlightbackground="#ec4899", relief="flat", cursor="hand2", padx=14, pady=8,
                                command=self._on_download_1688)
        btn_preview.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 8))

        # 按钮 3: 打开妙手采集箱
        btn_miaoshou = tk.Button(btn_row, text="🚀 3. 打开妙手采集箱", font=("Helvetica", 10, "bold"),
                                 bg="#3b82f6", fg="#1e293b", activebackground="#2563eb", activeforeground="#1e293b",
                                 highlightbackground="#3b82f6", relief="flat", cursor="hand2", padx=14, pady=8,
                                 command=self._on_open_miaoshou_collect)
        btn_miaoshou.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # 卡片 2: 当前商品信息展示（标题 + 链接 + 独立复制按钮）
        card_product = ttk.Frame(parent, style="Card.TFrame", padding="14 12 14 12")
        card_product.pack(fill=tk.X, pady=(0, 10))

        top_info_row = ttk.Frame(card_product, style="Card.TFrame")
        top_info_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top_info_row, text="📦 当前商品信息", style="Section.TLabel").pack(side=tk.LEFT)
        self.collect_info_tip = ttk.Label(top_info_row, text="（切到本页或点击下方采集自动回填）",
                                          font=("Helvetica", 8), foreground=self.text_secondary, style="Card.TLabel")
        self.collect_info_tip.pack(side=tk.LEFT, padx=(6, 0))

        # 商品标题行
        title_row = ttk.Frame(card_product, style="Card.TFrame")
        title_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(title_row, text="商品标题:", font=("Helvetica", 9, "bold"), style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.collect_title_var = tk.StringVar(value="等待采集...")
        self.collect_title_entry = tk.Entry(title_row, textvariable=self.collect_title_var, font=("Helvetica", 9),
                                            bg="#f8fafc", fg=self.text_primary, relief="solid", bd=1)
        self.collect_title_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)

        self.btn_copy_title = tk.Button(title_row, text="📋 复制标题", font=("Helvetica", 9, "bold"),
                                        bg="#3b82f6", fg="#1e293b", activebackground="#2563eb", activeforeground="#1e293b",
                                        highlightbackground="#3b82f6", relief="flat", cursor="hand2", padx=10, pady=2,
                                        command=self._on_copy_product_title)
        self.btn_copy_title.pack(side=tk.RIGHT)

        # 商品链接行
        url_row = ttk.Frame(card_product, style="Card.TFrame")
        url_row.pack(fill=tk.X)
        ttk.Label(url_row, text="商品链接:", font=("Helvetica", 9, "bold"), style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 6))
        self.collect_url_var = tk.StringVar(value="等待采集...")
        self.collect_url_entry = tk.Entry(url_row, textvariable=self.collect_url_var, font=("Helvetica", 9),
                                          bg="#f8fafc", fg=self.text_primary, relief="solid", bd=1)
        self.collect_url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6), ipady=3)

        self.btn_copy_url = tk.Button(url_row, text="📋 复制链接", font=("Helvetica", 9, "bold"),
                                      bg="#3b82f6", fg="#1e293b", activebackground="#2563eb", activeforeground="#1e293b",
                                      highlightbackground="#3b82f6", relief="flat", cursor="hand2", padx=10, pady=2,
                                      command=self._on_copy_product_url)
        self.btn_copy_url.pack(side=tk.RIGHT)

        # 卡片 3: 操作指引与流程说明
        card_guide = ttk.Frame(parent, style="Card.TFrame", padding="16 14 16 14")
        card_guide.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card_guide, text="💡 商品采集标准化工作流指引", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))

        steps = [
            ("步骤 1: 打开 1688 选品", "点击上方【打开 1688】在浏览器中搜索货源并进入目标商品详情页。"),
            ("步骤 2: 预览素材与选款下载", "在商品详情页点击【1688数据预览与采集】，弹出独立工作台分类预览主图、SKU 色卡与详情图，勾选后一键多线程写盘下载。"),
            ("步骤 3: 导入妙手采集箱", "点击【打开妙手采集箱】自动跳转至妙手通用采集箱 (linkCopy 模式)，粘贴链接批量采集入库。")
        ]

        for title, desc in steps:
            row = ttk.Frame(card_guide, style="Card.TFrame")
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=f"• {title}:", font=("Helvetica", 9, "bold"), style="Card.TLabel").pack(anchor=tk.W)
            ttk.Label(row, text=f"   {desc}", font=("Helvetica", 9), foreground=self.text_secondary, style="Card.TLabel").pack(anchor=tk.W)

    def _build_process_tab(self, parent):
        """构建【数据整理】菜单页面 (包含 SKU 录入工作台、JSON 数据管理与标准化流程指引)"""
        # 卡片 1: SKU 智能录入与核算控制台
        card_actions = ttk.Frame(parent, style="Card.TFrame", padding="16 14 16 14")
        card_actions.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(card_actions, text="📊 SKU 智能核算与录入工作台", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 6))
        ttk.Label(card_actions, text="点击下方按钮弹出独立 Chrome 工作台，填写商品规格与采购价，自动匹配全渠道最优物流并导出 JSON 数据。",
                  font=("Helvetica", 9), foreground=self.text_secondary, style="Card.TLabel").pack(anchor=tk.W, pady=(0, 10))

        btn_row = ttk.Frame(card_actions, style="Card.TFrame")
        btn_row.pack(fill=tk.X, pady=(0, 6))

        # 按钮 1: 弹出 SKU 录入工作台
        self.btn_sku_entry = tk.Button(btn_row, text="✨ 1. 弹出 SKU 录入工作台", font=("Helvetica", 10, "bold"),
                                       bg="#10b981", fg="#ffffff", activebackground="#059669", activeforeground="#ffffff",
                                       highlightbackground="#10b981", relief="flat", cursor="hand2", padx=16, pady=9,
                                       command=self._on_open_sku_calc)
        self.btn_sku_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 8))

        # 按钮 2: 打开数据导出目录
        self.btn_open_json_dir = tk.Button(btn_row, text="📂 2. 打开数据导出目录", font=("Helvetica", 10, "bold"),
                                           bg="#6366f1", fg="#ffffff", activebackground="#4f46e5", activeforeground="#ffffff",
                                           highlightbackground="#6366f1", relief="flat", cursor="hand2", padx=14, pady=9,
                                           command=self._on_open_export_dir)
        self.btn_open_json_dir.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 8))

        # 按钮 3: 复制最新 JSON 路径
        self.btn_copy_json_path = tk.Button(btn_row, text="📋 3. 复制最新 JSON 路径", font=("Helvetica", 10, "bold"),
                                            bg="#3b82f6", fg="#ffffff", activebackground="#2563eb", activeforeground="#ffffff",
                                            highlightbackground="#3b82f6", relief="flat", cursor="hand2", padx=14, pady=9,
                                            command=self._on_copy_latest_json_path)
        self.btn_copy_json_path.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # 卡片 2: 最近导出的 SKU 数据管理
        card_data = ttk.Frame(parent, style="Card.TFrame", padding="14 12 14 12")
        card_data.pack(fill=tk.X, pady=(0, 10))

        top_data_row = ttk.Frame(card_data, style="Card.TFrame")
        top_data_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top_data_row, text="📦 最近录入与导出状态", style="Section.TLabel").pack(side=tk.LEFT)

        self.lbl_json_status = tk.Label(top_data_row, text="🟢 就绪 (等待在工作台中录入并导出)",
                                        font=("Helvetica", 9, "bold"), bg=self.card_bg, fg="#64748b")
        self.lbl_json_status.pack(side=tk.RIGHT)

        # 文件路径行
        path_row = ttk.Frame(card_data, style="Card.TFrame")
        path_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(path_row, text="最新文件:", font=("Helvetica", 9, "bold"), style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 6))

        self.latest_json_path_var = tk.StringVar(value="")
        self.latest_json_entry = tk.Entry(path_row, textvariable=self.latest_json_path_var, font=("Helvetica", 9),
                                          bg="#f8fafc", fg=self.text_primary, relief="solid", bd=1)
        self.latest_json_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=3)

        # 详细信息行
        info_row = ttk.Frame(card_data, style="Card.TFrame")
        info_row.pack(fill=tk.X)
        self.latest_json_info_var = tk.StringVar(value="提示：在 Chrome 录入工作台中录入规格并点击【📥 导出 JSON 数据】后，此处将自动同步并记录。")
        self.lbl_json_info = ttk.Label(info_row, textvariable=self.latest_json_info_var,
                                       font=("Helvetica", 8), foreground=self.text_secondary, style="Card.TLabel")
        self.lbl_json_info.pack(side=tk.LEFT)

        # 卡片 3: 操作指引与标准化工作流说明
        card_guide = ttk.Frame(parent, style="Card.TFrame", padding="16 14 16 14")
        card_guide.pack(fill=tk.BOTH, expand=True)

        ttk.Label(card_guide, text="💡 数据整理与批量录入标准化工作流", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))

        flow_steps = [
            ("步骤 1: 采集素材与货源", "在【商品采集】页浏览 1688 详情页，点击预览采集多线程下载主图、SKU 色卡与详情图素材。"),
            ("步骤 2: 智能核算与录入", "点击上方【✨ 1. 弹出 SKU 录入工作台】，填写长宽高、实重、采购价与利润系数，系统自动推算全渠道运费并推荐最优解。"),
            ("步骤 3: 导出 JSON 数据", "在录入工作台中核算完成后点击【📥 导出 JSON 数据】，数据将自动下载并同步持久化到本地 sku_data_exports 目录。"),
            ("步骤 4: 妙手批量发布", "在【商品录入】页选择数据文件，点击开始批量录入，一键极速注入妙手采集箱或 ERP 批量刊登系统。")
        ]

        for title, desc in flow_steps:
            row = ttk.Frame(card_guide, style="Card.TFrame")
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=f"• {title}:", font=("Helvetica", 9, "bold"), style="Card.TLabel").pack(anchor=tk.W)
            ttk.Label(row, text=f"   {desc}", font=("Helvetica", 9), foreground=self.text_secondary, style="Card.TLabel").pack(anchor=tk.W)

    def _build_entry_tab(self, parent):
        """构建【商品录入】菜单页面 (妙手批量上传原有页面)"""
        # 1. 浏览器连接管理卡片
        self._create_browser_card(parent)

        # 2. 数据文件选择卡片
        self._create_file_card(parent)

        # 3. 操作与控制区域
        self._create_action_card(parent)

    def _create_browser_card(self, parent):
        """构建浏览器控制卡片"""
        card = ttk.Frame(parent, style="Card.TFrame", padding="12 10 12 10")
        card.pack(fill=tk.X, pady=(0, 10))

        # 标题行与指示灯
        top_row = ttk.Frame(card, style="Card.TFrame")
        top_row.pack(fill=tk.X, pady=(0, 8))

        lbl = ttk.Label(top_row, text="🌐 浏览器接管控制", style="Section.TLabel")
        lbl.pack(side=tk.LEFT)

        self.status_badge = tk.Label(top_row, text="🔴 未连接浏览器", font=("Helvetica", 9, "bold"),
                                     bg="#fee2e2", fg="#991b1b", padx=8, pady=2, relief="flat")
        self.status_badge.pack(side=tk.LEFT, padx=(12, 0))

        # 快捷启动按钮组 (支持一键打开妙手、1688 或刷新)
        btn_refresh = tk.Button(top_row, text="🔄 刷新列表", font=("Helvetica", 9),
                                bg="#e2e8f0", fg=self.text_primary, relief="flat", cursor="hand2",
                                padx=8, pady=2, command=self._async_refresh_browser_status)
        btn_refresh.pack(side=tk.RIGHT)

        btn_1688 = tk.Button(top_row, text="🛒 打开 1688", font=("Helvetica", 9, "bold"),
                             bg="#f97316", fg="#1e293b", activebackground="#ea580c", activeforeground="#1e293b",
                             highlightbackground="#f97316", relief="flat", cursor="hand2", padx=10, pady=2,
                             command=self._on_open_1688)
        btn_1688.pack(side=tk.RIGHT, padx=(0, 6))



        btn_launch = tk.Button(top_row, text="🚀 打开妙手", font=("Helvetica", 9, "bold"),
                               bg="#3b82f6", fg="#1e293b", activebackground="#2563eb", activeforeground="#1e293b",
                               highlightbackground="#3b82f6", relief="flat", cursor="hand2", padx=10, pady=2,
                               command=self._on_launch_browser)
        btn_launch.pack(side=tk.RIGHT, padx=(0, 6))

        # 标签页选择下拉框
        tab_row = ttk.Frame(card, style="Card.TFrame")
        tab_row.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(tab_row, text="目标标签页:", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 8))

        self.tab_var = tk.StringVar()
        self.tab_combo = ttk.Combobox(tab_row, textvariable=self.tab_var, state="readonly", width=70)
        self.tab_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 妙手账号密码配置行 (支持自动填入与持久化)
        cred_row = ttk.Frame(card, style="Card.TFrame")
        cred_row.pack(fill=tk.X)

        saved_creds = load_saved_credentials()
        ttk.Label(cred_row, text="妙手账号:", font=("Helvetica", 9), style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.acc_var = tk.StringVar(value=saved_creds.get("account", ""))
        self.acc_entry = ttk.Entry(cred_row, textvariable=self.acc_var, width=15, font=("Helvetica", 9))
        self.acc_entry.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(cred_row, text="密码:", font=("Helvetica", 9), style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        self.pwd_var = tk.StringVar(value=saved_creds.get("password", ""))
        self.pwd_entry = ttk.Entry(cred_row, textvariable=self.pwd_var, width=15, font=("Helvetica", 9), show="*")
        self.pwd_entry.pack(side=tk.LEFT, padx=(0, 8))

        btn_save_cred = tk.Button(cred_row, text="💾 保存账号密码", font=("Helvetica", 8),
                                  bg="#e2e8f0", fg=self.text_primary, relief="flat", cursor="hand2",
                                  padx=6, pady=1, command=self._on_save_credentials)
        btn_save_cred.pack(side=tk.LEFT)

        ttk.Label(cred_row, text="(配置后打开妙手可全自动免输入秒级登录)", font=("Helvetica", 8),
                  foreground=self.text_secondary, style="Card.TLabel").pack(side=tk.LEFT, padx=(8, 0))

    def _create_file_card(self, parent):
        """构建数据文件选择卡片"""
        card = ttk.Frame(parent, style="Card.TFrame", padding="12 10 12 10")
        card.pack(fill=tk.X, pady=(0, 10))

        # 标题
        top_row = ttk.Frame(card, style="Card.TFrame")
        top_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(top_row, text="📄 SKU 数据文件配置", style="Section.TLabel").pack(side=tk.LEFT)

        # 文件选择行
        file_row = ttk.Frame(card, style="Card.TFrame")
        file_row.pack(fill=tk.X, pady=(0, 6))

        self.file_path_var = tk.StringVar()
        self.file_entry = ttk.Entry(file_row, textvariable=self.file_path_var, font=("Helvetica", 9))
        self.file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        btn_browse = tk.Button(file_row, text="📂 浏览选择文件", font=("Helvetica", 9),
                               bg="#e2e8f0", fg=self.text_primary, relief="flat", cursor="hand2",
                               padx=10, pady=2, command=self._on_browse_file)
        btn_browse.pack(side=tk.RIGHT)

        # 解析统计信息显示区
        self.stat_label = ttk.Label(card, text="等待选择 .txt 数据文件...",
                                    style="Card.TLabel", foreground=self.text_secondary, font=("Helvetica", 9))
        self.stat_label.pack(fill=tk.X)

        # 默认填入当前工作区测试文件（如果存在）
        default_test = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "test_sku.txt"))
        if os.path.exists(default_test):
            self.file_path_var.set(default_test)
            self._parse_data_file(default_test, silent=True)

    def _create_action_card(self, parent):
        """构建操作按钮区域"""
        card = ttk.Frame(parent, style="Card.TFrame", padding="10 8 10 8")
        card.pack(fill=tk.X, pady=(0, 10))

        # 大号主按钮
        self.btn_run_all = tk.Button(card, text="▶ 一键全自动批量录入 (变体 + 图片 + 虚拟表格填入)",
                                     font=("Helvetica", 11, "bold"), bg="#10b981", fg="#1e293b",
                                     activebackground="#059669", activeforeground="#1e293b",
                                     highlightbackground="#10b981",
                                     relief="flat", cursor="hand2", pady=8, command=self._on_run_all)
        self.btn_run_all.pack(fill=tk.X, pady=(0, 6))

        # 单项辅助操作按钮组 (第 1 行：核心步骤单步调试)
        sub_row_1 = ttk.Frame(card, style="Card.TFrame")
        sub_row_1.pack(fill=tk.X, pady=(0, 5))

        self.btn_clean = tk.Button(sub_row_1, text="🧹 仅清理数据", font=("Helvetica", 9),
                                   bg="#f1f5f9", fg=self.text_primary, relief="flat", cursor="hand2",
                                   padx=6, pady=3, command=lambda: self._on_single_step("clean"))
        self.btn_clean.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.btn_variants = tk.Button(sub_row_1, text="🎨 仅添加变体维度", font=("Helvetica", 9),
                                      bg="#f1f5f9", fg=self.text_primary, relief="flat", cursor="hand2",
                                      padx=6, pady=3, command=lambda: self._on_single_step("variants"))
        self.btn_variants.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.btn_table = tk.Button(sub_row_1, text="📝 仅填表格", font=("Helvetica", 9),
                                   bg="#f1f5f9", fg=self.text_primary, relief="flat", cursor="hand2",
                                   padx=6, pady=3, command=lambda: self._on_single_step("table"))
        self.btn_table.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.btn_prod_img = tk.Button(sub_row_1, text="🖼️ 仅传产品图", font=("Helvetica", 9),
                                      bg="#f1f5f9", fg=self.text_primary, relief="flat", cursor="hand2",
                                      padx=6, pady=3, command=lambda: self._on_single_step("prod_img"))
        self.btn_prod_img.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.btn_sku_img = tk.Button(sub_row_1, text="📷 仅传SKU图", font=("Helvetica", 9),
                                     bg="#f1f5f9", fg=self.text_primary, relief="flat", cursor="hand2",
                                     padx=6, pady=3, command=lambda: self._on_single_step("sku_img"))
        self.btn_sku_img.pack(side=tk.LEFT, expand=True, fill=tk.X)

        # 单项辅助操作按钮组 (第 2 行：登录与辅助工具)
        sub_row_2 = ttk.Frame(card, style="Card.TFrame")
        sub_row_2.pack(fill=tk.X)

        self.btn_auto_login = tk.Button(sub_row_2, text="⚡ 自动过验证码登录", font=("Helvetica", 9, "bold"),
                                        bg="#fef3c7", fg="#b45309", relief="flat", cursor="hand2",
                                        padx=8, pady=3, command=self._on_auto_login)
        self.btn_auto_login.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.btn_check_1688 = tk.Button(sub_row_2, text="🔍 探测1688状态", font=("Helvetica", 9),
                                        bg="#fff7ed", fg="#c2410c", relief="flat", cursor="hand2",
                                        padx=8, pady=3, command=self._on_inspect_1688)
        self.btn_check_1688.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.btn_download_1688 = tk.Button(sub_row_2, text="🛒 1688素材预览与选款", font=("Helvetica", 9, "bold"),
                                           bg="#ec4899", fg="#1e293b", relief="flat", cursor="hand2",
                                           highlightbackground="#ec4899",
                                           padx=8, pady=3, command=self._on_download_1688)
        self.btn_download_1688.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.btn_test_upload = tk.Button(sub_row_2, text="🧪 测试SKU多图", font=("Helvetica", 9),
                                         bg="#e0e7ff", fg="#4338ca", relief="flat", cursor="hand2",
                                         padx=8, pady=3, command=lambda: self._on_single_step("test_upload"))
        self.btn_test_upload.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

        self.btn_stop = tk.Button(sub_row_2, text="🛑 停止", font=("Helvetica", 9, "bold"),
                                  bg="#ef4444", fg="#1e293b", relief="flat", cursor="hand2",
                                  highlightbackground="#ef4444",
                                  padx=10, pady=3, state=tk.DISABLED, command=self._on_stop_task)
        self.btn_stop.pack(side=tk.LEFT, padx=(4, 0))

    def _create_log_console(self, parent):
        """构建日志输出控制台"""
        log_frame = ttk.Frame(parent)
        log_frame.pack(fill=tk.BOTH, expand=True)

        top_bar = ttk.Frame(log_frame)
        top_bar.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(top_bar, text="📋 实时执行日志", font=("Helvetica", 10, "bold")).pack(side=tk.LEFT)

        btn_clear = tk.Button(top_bar, text="清空日志", font=("Helvetica", 8),
                              bg="#e2e8f0", fg=self.text_secondary, relief="flat", cursor="hand2",
                              padx=6, pady=1, command=self._clear_log)
        btn_clear.pack(side=tk.RIGHT)

        # 文本框与滚动条
        text_container = ttk.Frame(log_frame, style="Card.TFrame", padding="2 2 2 2")
        text_container.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(text_container, wrap="word", font=("Courier", 9),
                                bg="#1e293b", fg="#f8fafc", insertbackground="#ffffff",
                                relief="flat", padx=8, pady=8)
        scrollbar = ttk.Scrollbar(text_container, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 配置日志颜色标签
        self.log_text.tag_config("info", foreground="#94a3b8")
        self.log_text.tag_config("success", foreground="#34d399")
        self.log_text.tag_config("warn", foreground="#fbbf24")
        self.log_text.tag_config("error", foreground="#f87171")
        self.log_text.tag_config("time", foreground="#64748b")

    # =========================================================================
    # 界面交互与事件响应
    # =========================================================================
    def append_log(self, message: str, level: str = "info"):
        """向日志窗口输出彩色日志（线程安全）"""
        def _append():
            timestamp = time.strftime("[%H:%M:%S] ")
            self.log_text.insert(tk.END, timestamp, "time")
            self.log_text.insert(tk.END, message + "\n", level)
            self.log_text.see(tk.END)

        self.root.after(0, _append)

    def _clear_log(self):
        self.log_text.delete("1.0", tk.END)

    def _on_browse_file(self):
        """选择数据文件"""
        file_path = filedialog.askopenfilename(
            title="选择 SKU 数据文件",
            filetypes=[("Text files", "*.txt"), ("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if file_path:
            self.file_path_var.set(file_path)
            self._parse_data_file(file_path)

    def _parse_data_file(self, file_path: str, silent: bool = False):
        """解析并展示数据文件概况"""
        try:
            bundle = SkuParser.parse_file(file_path)
            self.current_bundle = bundle
            stat_text = (
                f"✅ 解析成功！共 {bundle.total_sku_count} 个 SKU | "
                f"颜色: {len(bundle.unique_colors)} 种 ({', '.join(bundle.unique_colors[:4])}{'...' if len(bundle.unique_colors)>4 else ''}) | "
                f"尺码: {len(bundle.unique_sizes)} 种 | "
                f"产品主图: {'已就绪' if bundle.main_image_full_path else '无'} | "
                f"详情图: {len(bundle.detail_image_full_paths)} 张"
            )
            self.stat_label.configure(text=stat_text, foreground="#059669")
            if not silent:
                self.append_log(f"成功解析数据文件: {os.path.basename(file_path)} (共 {bundle.total_sku_count} 条 SKU)", "success")
                if bundle.warnings:
                    for w in bundle.warnings:
                        self.append_log(f"⚠️ 解析提示: {w}", "warn")
        except Exception as e:
            self.current_bundle = None
            self.stat_label.configure(text=f"❌ 文件解析失败: {str(e)}", foreground="#dc2626")
            if not silent:
                self.append_log(f"文件解析失败: {str(e)}", "error")

    def _on_save_credentials(self):
        """保存账号密码配置"""
        acc = self.acc_var.get().strip()
        pwd = self.pwd_var.get().strip()
        save_credentials(acc, pwd, remember=True)
        self.append_log("✅ 妙手账号密码已成功保存到本地安全配置", "success")

    def _on_launch_browser(self):
        """启动/唤起浏览器（直达妙手）并在最右侧新开标签页，自动填入登录信息并秒登"""
        self.append_log(f"正在打开妙手工作台 ({config.MIAOSHOU_HOME_URL})...", "info")

        def _worker():
            if not self.browser_mgr.is_cdp_ready():
                ok, msg = self.browser_mgr.launch_managed_chrome(initial_url=config.MIAOSHOU_HOME_URL)
                if not ok:
                    self.append_log(f"❌ {msg}", "error")
                    return
                self.append_log(f"✅ {msg}", "success")
                time.sleep(1.0)
                # 恢复历史会话后，在最右侧新开妙手页签
                self.browser_mgr.open_new_tab(config.MIAOSHOU_HOME_URL)
            else:
                # 浏览器已在运行：记录已有标签页数量，在最右侧新开
                existing_count = self.browser_mgr.get_open_tab_count()
                self.append_log(f"📑 当前浏览器已有 {existing_count} 个标签页，将在最右侧新开页签...", "info")
                self.browser_mgr.open_new_tab(config.MIAOSHOU_HOME_URL)

            # 确保最右侧标签页被激活并展示在前台
            time.sleep(0.3)
            self.browser_mgr.bring_browser_to_front(select_last_tab=True)
            self.root.after(400, self._async_refresh_browser_status)

            # ★ 关键：重新获取当前浏览器真正展示在最前台的活动页面
            # AppleScript 创建标签页后返回的 Playwright Page 对象可能不精确，
            # 必须在确认最右侧标签页激活后，通过 get_active_page 拿到真实页面
            time.sleep(0.8)
            active_p = self.browser_mgr.get_active_page()
            if not active_p:
                # 兜底：取 context 中最后一个页面（即最右侧）
                try:
                    ok, _ = self.browser_mgr.connect(activate=False, auto_create_tab=False)
                    if ok and self.browser_mgr.context and self.browser_mgr.context.pages:
                        active_p = self.browser_mgr.context.pages[-1]
                except Exception:
                    pass

            if active_p:
                self.append_log("✨ 已在浏览器最右侧新开妙手标签页并置顶！", "success")

                # 在最右侧新页面上执行自动登录检测与填入
                def _do_auto_login_on_thread():
                    try:
                        active_p.wait_for_load_state("domcontentloaded", timeout=6000)
                    except Exception:
                        pass
                    time.sleep(0.8)
                    helper = MiaoshouLoginHelper(active_p, log_fn=self.append_log)
                    if helper.is_login_page():
                        acc = self.acc_var.get().strip()
                        pwd = self.pwd_var.get().strip()
                        helper.auto_solve_captcha_and_login(acc, pwd)

                time.sleep(0.5)
                self.browser_mgr.run_on_browser_thread(_do_auto_login_on_thread)
                self.root.after(500, self._async_refresh_browser_status)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_auto_login(self):
        """手动一键触发当前妙手页面的自动识别验证码与登录"""
        def _worker():
            # 1. 确保浏览器处于连接状态
            if not self.browser_mgr.is_cdp_ready():
                self.append_log("未检测到运行中的浏览器，正在启动 Chrome...", "info")
                ok, msg = self.browser_mgr.launch_managed_chrome(initial_url=config.MIAOSHOU_HOME_URL)
                if not ok:
                    self.append_log(f"❌ {msg}", "error")
                    return
                time.sleep(1.5)

            # 2. 获取妙手目标标签页
            target_p = self._get_target_page()
            if not target_p:
                target_p = self.browser_mgr.open_or_focus_url(config.MIAOSHOU_HOME_URL)

            if not target_p:
                self.append_log("❌ 未能连接到妙手标签页，请先在浏览器中打开页面", "error")
                return

            # 3. 自动识别并登录
            acc = self.acc_var.get().strip()
            pwd = self.pwd_var.get().strip()
            helper = MiaoshouLoginHelper(target_p, log_fn=self.append_log)
            self.browser_mgr.run_on_browser_thread(helper.auto_solve_captcha_and_login, acc, pwd)
            self.root.after(300, self._async_refresh_browser_status)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_open_1688(self):
        """启动/唤起浏览器并直达 1688"""
        self.append_log(f"正在打开 1688 货源平台 ({config.URL_1688_HOME})...", "info")

        def _worker():
            if not self.browser_mgr.is_cdp_ready():
                ok, msg = self.browser_mgr.launch_managed_chrome(initial_url=config.URL_1688_HOME)
                if ok:
                    self.append_log(f"✅ {msg}", "success")
                else:
                    self.append_log(f"❌ {msg}", "error")
            else:
                self.browser_mgr.open_new_tab(config.URL_1688_HOME)
                self.append_log("✨ 已在浏览器最右侧新开 1688 标签页！", "success")

            self.browser_mgr.bring_browser_to_front()
            self.root.after(300, self._async_refresh_browser_status)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_open_miaoshou_collect(self):
        """在 Chrome 中打开妙手通用采集箱 (linkCopy 模式)"""
        target_url = "https://erp.91miaoshou.com/common_collect_box/index?fetchType=linkCopy"
        self.append_log(f"正在打开妙手采集箱: {target_url} ...", "info")

        def _worker():
            if not self.browser_mgr.is_cdp_ready():
                ok, msg = self.browser_mgr.launch_managed_chrome(initial_url=target_url)
                if ok:
                    self.append_log("✨ 成功拉起 Chrome 并打开妙手采集箱！", "success")
                else:
                    self.append_log(f"❌ {msg}", "error")
            else:
                self.browser_mgr.open_new_tab(target_url)
                self.append_log("✨ 已在浏览器最右侧新开妙手标签页！", "success")

            self.browser_mgr.bring_browser_to_front()
            self.root.after(300, self._async_refresh_browser_status)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_inspect_1688(self):
        """读取并检查当前 1688 页面的登录态与基本信息"""
        page = self._get_target_page()
        if not page:
            messagebox.showwarning("提示", "未找到可操作的标签页，请先在上方下拉框选择 1688 标签页！")
            return

        def _worker():
            self.append_log(f"正在检测当前选中页面的 1688 登录状态: {page.url} ...", "info")
            scraper = Scraper1688(page, log_fn=self.append_log)
            is_login = self.browser_mgr.run_on_browser_thread(scraper.is_logged_in)
            if is_login:
                self.append_log("🟢 1688 登录状态正常！已检测到用户会话，无需重新登录。", "success")
            else:
                self.append_log("⚠️ 未检测到 1688 登录态，若未登录请在浏览器中扫码登录一次（登录后会自动持久化）。", "warn")

        threading.Thread(target=_worker, daemon=True).start()

    def _async_probe_1688_info(self):
        """在后台轻量探测当前打开的 1688 商品详情页标题与链接，毫秒级回填"""
        def _worker():
            try:
                if not self.browser_mgr.is_cdp_ready():
                    return
                tabs = self.browser_mgr.get_all_tabs()
                detail_tab = None
                # 1. 优先获取当前正在显示的 1688 详情页
                for t in tabs:
                    if t.is_active and ("detail.1688.com" in (t.url or "") or "/offer/" in (t.url or "")) and "127.0.0.1" not in (t.url or "") and "localhost" not in (t.url or ""):
                        detail_tab = t
                        break
                        
                # 2. 如果前台没有任何 1688 详情页面激活，兜底找最后一个打开的 1688 详情页
                if not detail_tab:
                    for t in reversed(tabs):
                        if ("detail.1688.com" in (t.url or "") or "/offer/" in (t.url or "")) and "127.0.0.1" not in (t.url or "") and "localhost" not in (t.url or ""):
                            detail_tab = t
                            break
                if detail_tab:
                    u = detail_tab.url or ""
                    raw_t = detail_tab.title or ""
                    clean_t = raw_t.split('-')[0].replace('【阿里巴巴】', '').replace('- 阿里巴巴', '').strip()
                    if not clean_t:
                        clean_t = raw_t.strip()
                    if clean_t or u:
                        self.root.after(0, lambda: self._update_collect_product_info(clean_t, u))
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _on_download_1688(self):
        """直接在 Chrome 中弹出 1688-Image-Downloader 插件原生独立窗口 (方案 A)"""
        # 1. 确保 Chrome 浏览器已连接/已启动
        if not self.browser_mgr.is_cdp_ready():
            self.append_log("未检测到运行中的 Chrome 浏览器，正在启动...", "info")
            ok, msg = self.browser_mgr.launch_managed_chrome(initial_url=config.URL_1688_HOME)
            if not ok:
                self.append_log(f"❌ {msg}", "error")
                messagebox.showerror("启动失败", msg)
                return
            time.sleep(1.5)

        # 2. 立即主动探测并回填当前 1688 页面标题与链接
        self._async_probe_1688_info()

        # 3. 立即唤起 Chrome 插件原生独立工作台窗口
        self.append_log("正在唤起 Chrome 1688 插件原生工作台独立窗口...", "info")
        ok = self.browser_mgr.open_1688_extension_popup()
        if ok:
            self.append_log("✨ 已成功弹出 1688 插件原生独立工作台窗口！", "success")
        else:
            self.append_log("⚠️ 唤起插件窗口未成功，请检查插件目录路径", "warn")

    def _on_open_sku_calc(self):
        """弹出独立 Chrome 窗口展示 calcfee SKU 录入与核算工作台"""
        # 1. 确保 Chrome 浏览器已连接/已启动
        if not self.browser_mgr.is_cdp_ready():
            self.append_log("未检测到运行中的 Chrome 浏览器，正在启动...", "info")
            calcfee_url = PluginServerManager.get_calcfee_url()
            ok, msg = self.browser_mgr.launch_managed_chrome(initial_url=calcfee_url)
            if not ok:
                self.append_log(f"❌ {msg}", "error")
                messagebox.showerror("启动失败", msg)
                return
            time.sleep(1.5)

        # 2. 唤起 Chrome 原生独立工作台窗口
        self.append_log("正在唤起 Chrome SKU 录入与核算工作台独立窗口...", "info")
        ok = self.browser_mgr.open_calcfee_popup()
        if ok:
            self.append_log("✨ 已成功弹出 SKU 录入与核算工作台独立窗口！", "success")
        else:
            self.append_log("⚠️ 唤起工作台窗口未成功，请检查服务状态", "warn")

    def _on_open_export_dir(self):
        """打开数据导出目录 (test产品试验品)"""
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        target_dir = os.path.join(base_dir, "test产品试验品")
        os.makedirs(target_dir, exist_ok=True)

        if sys.platform == "darwin":
            subprocess.Popen(["open", target_dir])
        elif sys.platform == "win32":
            os.startfile(target_dir)
        else:
            subprocess.Popen(["xdg-open", target_dir])

        self.append_log(f"📂 已打开数据导出目录: {target_dir}", "info")

    def _on_copy_latest_json_path(self):
        """复制最新导出的 JSON 文件完整路径"""
        path = self.latest_json_path_var.get().strip() if hasattr(self, 'latest_json_path_var') else ""
        if not path or not os.path.exists(path):
            messagebox.showinfo("提示", "暂无最新导出的 JSON 文件，请先在工作台中录入并导出！")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(path)
        self.root.update()
        self.append_log(f"📋 已复制最新 JSON 路径到剪贴板: {path}", "success")

    def _on_calcfee_export_callback(self, file_path: str, count: int):
        """当前端录入系统导出 JSON 时，主程序实时同步状态与日志"""
        def _update():
            if hasattr(self, 'latest_json_path_var'):
                self.latest_json_path_var.set(file_path)
            if hasattr(self, 'latest_json_info_var'):
                self.latest_json_info_var.set(f"包含条目: {count} 条 | 导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            if hasattr(self, 'lbl_json_status'):
                self.lbl_json_status.configure(text=f"🟢 最新导出: {os.path.basename(file_path)} (共 {count} 条)", fg="#10b981")
            self.append_log(f"📥 成功接收并保存导出的 SKU 数据: {os.path.basename(file_path)} (共 {count} 条条目)", "success")
        self.root.after(0, _update)

    def _on_plugin_scan_callback(self, title: str, url: str):
        """当本地插件服务完成扫描时，自动同步更新 GUI 商品信息"""
        self.root.after(0, lambda: self._update_collect_product_info(title, url))

    def _update_collect_product_info(self, title: str, url: str):
        """更新商品采集工作台中的商品标题与链接信息"""
        clean_title = (title or "").strip()
        if clean_title:
            self.collect_title_var.set(clean_title)
        clean_url = (url or "").strip()
        if clean_url:
            self.collect_url_var.set(clean_url)
        if hasattr(self, 'collect_info_tip'):
            self.collect_info_tip.configure(text="（已就绪，可一键复制）", foreground="#10b981")
        self.append_log(f"📦 已自动获取并更新商品信息: {clean_title[:35]}...", "success")

    def _on_copy_product_title(self):
        """复制当前商品标题到剪贴板"""
        title = self.collect_title_var.get()
        if not title or title in ("等待采集...", "⏳ 正在采集 1688 商品数据..."):
            messagebox.showinfo("提示", "暂无商品标题，请先点击【1688数据预览与采集】获取商品信息！")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(title)
        self.root.update()
        orig_text = self.btn_copy_title.cget("text")
        orig_bg = self.btn_copy_title.cget("bg")
        self.btn_copy_title.configure(text="✅ 已复制!", bg="#10b981")
        self.append_log(f"📋 商品标题已复制到剪贴板: {title}", "success")
        self.root.after(2000, lambda: self.btn_copy_title.configure(text=orig_text, bg=orig_bg))

    def _on_copy_product_url(self):
        """复制当前商品链接到剪贴板"""
        url = self.collect_url_var.get()
        if not url or url in ("等待采集...", "⏳ 正在解析商品链接..."):
            messagebox.showinfo("提示", "暂无商品链接，请先点击【1688数据预览与采集】获取商品信息！")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self.root.update()
        orig_text = self.btn_copy_url.cget("text")
        orig_bg = self.btn_copy_url.cget("bg")
        self.btn_copy_url.configure(text="✅ 已复制!", bg="#10b981")
        self.append_log(f"📋 商品链接已复制到剪贴板: {url}", "success")
        self.root.after(2000, lambda: self.btn_copy_url.configure(text=orig_text, bg=orig_bg))

    def _async_refresh_browser_status(self):
        """异步刷新浏览器状态与标签页列表"""
        def _worker():
            is_ready = self.browser_mgr.is_cdp_ready()
            if not is_ready:
                self.root.after(0, lambda: self._update_browser_ui(False, []))
                return

            ok, _ = self.browser_mgr.connect(activate=False, auto_create_tab=False)
            if ok:
                tabs = self.browser_mgr.get_all_tabs()
                self.root.after(0, lambda: self._update_browser_ui(True, tabs))
            else:
                self.root.after(0, lambda: self._update_browser_ui(False, []))

        threading.Thread(target=_worker, daemon=True).start()

    def _update_browser_ui(self, is_connected: bool, tabs: List[TabInfo]):
        """更新浏览器连接状态显示与标签页下拉列表"""
        self.available_tabs = tabs
        if is_connected:
            self.status_badge.configure(text="🟢 浏览器已连接", bg="#d1fae5", fg="#065f46")
            tab_options = [t.display_text() for t in tabs]
            self.tab_combo["values"] = tab_options

            # 优先选中当前正在显示的页签，其次第一个妙手标签页，最后兜底第一个页面
            selected_idx = 0
            for idx, t in enumerate(tabs):
                if t.is_active:
                    selected_idx = idx
                    break
            else:
                for idx, t in enumerate(tabs):
                    if t.is_miaoshou:
                        selected_idx = idx
                        break

            if tab_options:
                self.tab_combo.current(selected_idx)
                self.append_log(f"已识别到 {len(tabs)} 个标签页，当前锁定: {tabs[selected_idx].title}", "info")
        else:
            self.status_badge.configure(text="🔴 浏览器未连接", bg="#fee2e2", fg="#991b1b")
            self.tab_combo["values"] = ["(请先点击上方【启动浏览器】并在 Chrome 中打开妙手页面)"]
            self.tab_combo.current(0)

    def _get_target_page(self):
        """
        获取当前待操作的 Page 对象：
        时刻以浏览器当前真正处于前台展示/激活的页签为准；
        如果未获取到或不在前台，则以用户下拉框选择或匹配到的活动页为准。
        """
        # 1. 优先获取当前浏览器最前台、正在展示的活动标签页
        active_page = self.browser_mgr.get_active_page()
        if active_page:
            return active_page

        # 2. 其次获取下拉框当前选中的标签页
        if self.available_tabs:
            curr_idx = self.tab_combo.current()
            if 0 <= curr_idx < len(self.available_tabs):
                return self.available_tabs[curr_idx].page

        # 3. 兜底获取
        return self.browser_mgr.find_best_target_page()

    def _set_ui_running(self, running: bool):
        """切换运行中/空闲状态的按键状态"""
        self.is_running = running
        state = tk.DISABLED if running else tk.NORMAL
        self.btn_run_all.configure(state=state)
        self.btn_clean.configure(state=state)
        self.btn_variants.configure(state=state)
        self.btn_prod_img.configure(state=state)
        self.btn_sku_img.configure(state=state)
        self.btn_table.configure(state=state)
        self.btn_auto_login.configure(state=state)
        self.btn_check_1688.configure(state=state)
        self.btn_test_upload.configure(state=state)
        self.btn_stop.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _on_stop_task(self):
        """取消当前任务"""
        if self.current_executor:
            self.current_executor.cancel()

    def _on_run_all(self):
        """一键全自动录入流程"""
        if not self._validate_ready():
            return

        self._set_ui_running(True)
        target_page = self._get_target_page()
        executor = SkuExecutor(target_page, self.current_bundle, log_fn=self.append_log)
        self.current_executor = executor

        def _worker():
            try:
                def _run():
                    try:
                        t_str = target_page.title()
                        u_str = target_page.url
                        self.append_log(f"🎯 目标锁定当前展示页面: {t_str} ({u_str[:45]}...)", "info")
                    except Exception:
                        pass
                    executor.run_all()
                self.browser_mgr.run_on_browser_thread(_run)
            except Exception as e:
                self.append_log(f"自动化执行异常: {str(e)}", "error")
            finally:
                self.root.after(0, lambda: self._set_ui_running(False))
                self.current_executor = None

        threading.Thread(target=_worker, daemon=True).start()

    def _on_single_step(self, step_name: str):
        """执行单步操作（仅清理、仅生成变体、仅传图等）"""
        if self.is_running:
            messagebox.showwarning("提示", "当前已有任务正在运行中，请稍候！")
            return

        target_page = self._get_target_page()
        if not target_page:
            messagebox.showwarning("提示", "未找到可操作的标签页，请先在上方下拉框选择妙手编辑页！")
            return

        # 变体、传图、填表需要有数据文件，但纯清理不需要
        if step_name != "clean" and (not self.current_bundle or not self.current_bundle.items):
            messagebox.showwarning("缺少数据", "请先选择有效的 .txt 数据文件！")
            return

        self._set_ui_running(True)
        dummy_bundle = self.current_bundle or SkuDataBundle(base_dir="", product_dir="", main_image="", detail_dir="", sku_dir="", headers=[], items=[], warnings=[])
        executor = SkuExecutor(target_page, dummy_bundle, log_fn=self.append_log)
        self.current_executor = executor

        def _worker():
            try:
                def _do_step():
                    try:
                        t_str = target_page.title()
                        u_str = target_page.url
                        self.append_log(f"🎯 目标锁定当前展示页面: {t_str} ({u_str[:45]}...)", "info")
                    except Exception:
                        pass
                    if step_name == "clean":
                        executor.clean_existing_data()
                    elif step_name == "variants":
                        executor.clean_existing_data()
                        executor.setup_variants()
                    elif step_name == "prod_img":
                        executor.upload_product_images()
                    elif step_name == "sku_img":
                        executor.upload_sku_images()
                    elif step_name == "test_upload":
                        executor.test_upload_first_sku_images()
                    elif step_name == "table":
                        executor.fill_virtual_table()
                self.browser_mgr.run_on_browser_thread(_do_step)
            except Exception as e:
                self.append_log(f"单步执行异常: {str(e)}", "error")
            finally:
                self.root.after(0, lambda: self._set_ui_running(False))
                self.current_executor = None

        threading.Thread(target=_worker, daemon=True).start()

    def _validate_ready(self) -> bool:
        """运行前校验"""
        if self.is_running:
            messagebox.showwarning("提示", "当前已有任务正在运行中，请稍候！")
            return False

        if not self.current_bundle or not self.current_bundle.items:
            messagebox.showwarning("缺少数据", "请先选择有效的 .txt 数据文件！")
            return False

        if not self.browser_mgr.is_cdp_ready():
            messagebox.showwarning("浏览器未连接", "未检测到调试浏览器，请先点击【启动/打开妙手浏览器】！")
            return False

        page = self._get_target_page()
        if not page:
            messagebox.showwarning("未找到页面", "未能锁定妙手编辑页面，请确保在浏览器中打开了商品编辑页！")
            return False

        return True


def auto_nav_quick_listing_amazon(page, log_fn):
    """在妙手后台自动点击左侧功能菜单：快速上货 -> Amazon"""
    try:
        # 等待后台框架/菜单渲染（最多 10 秒）
        for _ in range(20):
            try:
                if page.locator(".basic-layout-side, .jx-menu, .el-menu, [class*='menu'], [class*='aside']").count() > 0:
                    break
            except Exception:
                pass
            time.sleep(0.5)

        js_click_menu = r"""
        async () => {
          const visible = (el) => {
            const r = el.getBoundingClientRect();
            const s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
          };
          const norm = (el) => (el.textContent || '').replace(/\s+/g, '').trim();
          const findBest = (text, root) => {
            const scope = root || document;
            const cands = Array.from(scope.querySelectorAll('li, a, div, span, button'))
              .filter(el => {
                if (!visible(el)) return false;
                const t = norm(el);
                return t === text || t.startsWith(text);
              });
            // 文本最短的通常是最内层菜单项
            cands.sort((a, b) => a.textContent.length - b.textContent.length);
            return cands[0] || null;
          };
          const realClick = (el) => {
            el.scrollIntoView({ block: 'center' });
            ['mouseover', 'mouseenter', 'mousedown', 'mouseup', 'click'].forEach(evt => {
              const EvtCtor = evt.startsWith('mouse') || evt === 'click' ? MouseEvent : Event;
              el.dispatchEvent(new EvtCtor(evt, { bubbles: true, cancelable: true, view: window }));
            });
            if (typeof el.click === 'function') el.click();
          };

          // 1. 点击【快速上货】菜单（展开子菜单）
          const quickMenu = findBest('快速上货');
          if (!quickMenu) return { success: false, msg: '未找到【快速上货】菜单项（页面可能尚未加载完成）' };
          realClick(quickMenu);
          await new Promise(r => setTimeout(r, 800));

          // 2. 优先在【快速上货】所属菜单容器内查找【Amazon】子项
          let amazonItem = null;
          let container = quickMenu.closest('li') || quickMenu.parentElement;
          for (let depth = 0; depth < 5 && container; depth++) {
            amazonItem = findBest('Amazon', container);
            if (amazonItem) break;
            container = container.parentElement;
          }
          // 兜底：全局查找（兼容悬浮弹出的子菜单）
          if (!amazonItem) {
            await new Promise(r => setTimeout(r, 300));
            amazonItem = findBest('Amazon');
          }
          if (!amazonItem) return { success: false, msg: '已展开【快速上货】，但未找到【Amazon】子菜单' };

          realClick(amazonItem);
          await new Promise(r => setTimeout(r, 500));
          return { success: true };
        }
        """
        res = page.evaluate(js_click_menu)
        if res.get("success"):
            log_fn("✅ 已自动点击功能菜单：快速上货 -> Amazon", "success")
        else:
            log_fn(f"⚠️ 菜单自动点击未完成: {res.get('msg')}", "warn")
    except Exception as e:
        log_fn(f"⚠️ 自动点击【快速上货-Amazon】异常: {str(e)}", "warn")


def start_app():
    """启动桌面应用入口"""
    root = tk.Tk()

    # 针对 macOS Dock 栏图标点击唤醒与最小化还原的系统级修复
    if sys.platform == "darwin":
        def _on_mac_reopen(*args):
            try:
                # 若窗口处于最小化 (iconic) 或隐藏 (withdrawn) 状态，还原为正常状态
                if root.state() in ("iconic", "withdrawn"):
                    root.deiconify()
                    root.state("normal")
                root.lift()
                root.focus_force()
            except Exception:
                pass

        try:
            root.createcommand("::tk::mac::ReopenApplication", _on_mac_reopen)
        except Exception:
            pass

    app = SkuAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    start_app()

