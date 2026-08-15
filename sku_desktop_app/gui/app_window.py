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


class SkuAppGUI:
    """主桌面 GUI 应用程序"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("妙手 SKU 智能批量录入助手 v2.0 (接管模式)")
        self.root.geometry("860x680")
        self.root.minsize(800, 600)

        # 核心控制器
        self.browser_mgr = BrowserManager()
        self.current_bundle: Optional[SkuDataBundle] = None
        self.current_executor: Optional[SkuExecutor] = None
        self.available_tabs: List[TabInfo] = []
        self.is_running = False

        # 初始化样式与界面布局
        self._setup_styles()
        self._create_widgets()

        # 启动后自动检查一次浏览器状态
        self.root.after(500, self._async_refresh_browser_status)

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

    def _create_widgets(self):
        """构建界面主要组件"""
        # 主滚动容器/外边距容器
        main_container = ttk.Frame(self.root, padding="16 16 16 16")
        main_container.pack(fill=tk.BOTH, expand=True)

        # 1. 顶部标题与状态栏
        header_frame = ttk.Frame(main_container)
        header_frame.pack(fill=tk.X, pady=(0, 12))

        title_label = ttk.Label(header_frame, text="🤖 妙手 SKU 批量自动化录入助手", style="Header.TLabel")
        title_label.pack(side=tk.LEFT)

        sub_label = ttk.Label(header_frame, text="原生接管模式 • 零配置免服务", font=("Helvetica", 9), foreground=self.text_secondary)
        sub_label.pack(side=tk.LEFT, padx=(10, 0), pady=(4, 0))

        # 2. 浏览器连接管理卡片
        self._create_browser_card(main_container)

        # 3. 数据文件选择卡片
        self._create_file_card(main_container)

        # 4. 操作与控制区域
        self._create_action_card(main_container)

        # 5. 日志监控窗口
        self._create_log_console(main_container)

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

        self.btn_download_1688 = tk.Button(sub_row_2, text="🛒 抓取1688数据", font=("Helvetica", 9, "bold"),
                                           bg="#ec4899", fg="#1e293b", relief="flat", cursor="hand2",
                                           highlightbackground="#ec4899",
                                           padx=8, pady=3, command=self._on_download_1688)
        self.btn_download_1688.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))

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
        """启动/唤起浏览器（直达妙手）并在检测到登录页时自动识别验证码秒登"""
        self.append_log(f"正在打开妙手工作台 ({config.MIAOSHOU_HOME_URL})...", "info")

        def _worker():
            if not self.browser_mgr.is_cdp_ready():
                ok, msg = self.browser_mgr.launch_managed_chrome(initial_url=config.MIAOSHOU_HOME_URL)
                if ok:
                    self.append_log(f"✅ {msg}", "success")
                else:
                    self.append_log(f"❌ {msg}", "error")
                    return
            else:
                self.browser_mgr.open_or_focus_url(config.MIAOSHOU_HOME_URL)
                self.append_log("已在当前浏览器中定位/打开妙手工作台标签页", "success")

            self.root.after(400, self._async_refresh_browser_status)

            # 智能检测：如果处于登录页且有验证码，自动启动 AI OCR 秒级过码登录
            time.sleep(1.5)
            target_p = self._get_target_page()
            if target_p:
                helper = MiaoshouLoginHelper(target_p, log_fn=self.append_log)
                if self.browser_mgr.run_on_browser_thread(helper.is_login_page):
                    acc = self.acc_var.get().strip()
                    pwd = self.pwd_var.get().strip()
                    self.browser_mgr.run_on_browser_thread(helper.auto_solve_captcha_and_login, acc, pwd)
                    time.sleep(2.0)
                # 登录就绪后，自动点击左侧功能菜单：快速上货 -> Amazon
                self.browser_mgr.run_on_browser_thread(auto_nav_quick_listing_amazon, target_p, self.append_log)

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
                self.browser_mgr.open_or_focus_url(config.URL_1688_HOME)
                self.append_log("已在当前浏览器中定位/打开 1688 标签页", "success")

            self.root.after(300, self._async_refresh_browser_status)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_inspect_1688(self):
        """读取并检查当前 1688 页面的登录态与预览信息"""
        page = self._get_target_page()
        if not page:
            messagebox.showwarning("提示", "未找到可操作的标签页，请先在下拉框选择 1688 标签页！")
            return

        def _worker():
            self.append_log(f"正在检测当前选中页面的 1688 登录状态与数据: {page.url} ...", "info")
            scraper = Scraper1688(page)
            is_login = self.browser_mgr.run_on_browser_thread(scraper.is_logged_in)
            if is_login:
                self.append_log("🟢 1688 登录状态正常！已检测到用户会话，无需重新登录。", "success")
            else:
                self.append_log("⚠️ 未检测到 1688 登录态，若未登录请在浏览器中扫码登录一次（登录后会自动持久化）。", "warn")

            data = self.browser_mgr.run_on_browser_thread(scraper.extract_product_preview)
            title = data.get("title", "")
            imgs = data.get("main_images", [])
            self.append_log(f"📄 1688 页面标题: {title}", "info")
            if imgs:
                self.append_log(f"🖼️ 检测到主图数量: {len(imgs)} 张", "info")

        threading.Thread(target=_worker, daemon=True).start()

    def _on_download_1688(self):
        """一键抓取并下载 1688 当前页面的变体、图片和 SKU 数据"""
        page = self._get_target_page()
        if not page:
            messagebox.showwarning("提示", "未找到可操作的标签页，请先在下拉框选择 1688 标签页！")
            return
            
        file_path = self.file_path_var.get()
        if file_path and os.path.exists(os.path.dirname(file_path)):
            base_dir = os.path.dirname(file_path)
        else:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            
        self._set_ui_running(True)
        def _worker():
            try:
                self.append_log(f"准备从 {page.url} 提取 1688 数据...", "info")
                scraper = Scraper1688(page, log_fn=self.append_log)
                self.browser_mgr.run_on_browser_thread(lambda: scraper.extract_and_download(base_dir))
            except Exception as e:
                self.append_log(f"1688 数据抓取异常: {str(e)}", "error")
            finally:
                self.root.after(0, lambda: self._set_ui_running(False))
                
        threading.Thread(target=_worker, daemon=True).start()

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
        """获取当前用户在下拉框选中的 Page 对象"""
        if not self.available_tabs:
            # 尝试自动查找
            return self.browser_mgr.find_best_target_page()

        curr_idx = self.tab_combo.current()
        if 0 <= curr_idx < len(self.available_tabs):
            return self.available_tabs[curr_idx].page

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
                self.browser_mgr.run_on_browser_thread(executor.run_all)
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
                if step_name == "clean":
                    self.browser_mgr.run_on_browser_thread(executor.clean_existing_data)
                elif step_name == "variants":
                    def _step_variants():
                        executor.clean_existing_data()
                        executor.setup_variants()
                    self.browser_mgr.run_on_browser_thread(_step_variants)
                elif step_name == "prod_img":
                    self.browser_mgr.run_on_browser_thread(executor.upload_product_images)
                elif step_name == "sku_img":
                    self.browser_mgr.run_on_browser_thread(executor.upload_sku_images)
                elif step_name == "table":
                    self.browser_mgr.run_on_browser_thread(executor.fill_virtual_table)
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
    app = SkuAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    start_app()
