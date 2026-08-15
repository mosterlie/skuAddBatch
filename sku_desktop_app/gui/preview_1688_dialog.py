"""
1688 素材分类预览、筛选与按需下载工作台弹窗
"""
import os
import sys
import io
import time
import json
import threading
import subprocess
import requests
from typing import Dict, Any, List, Optional
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.scraper_1688 import Scraper1688


class Preview1688Dialog(tk.Toplevel):
    """1688 素材分类预览与按需下载工作台"""

    def __init__(self, parent: tk.Widget, raw_data: Dict[str, Any], scraper: Scraper1688, default_output_dir: str = ""):
        super().__init__(parent)
        self.raw_data = raw_data
        self.scraper = scraper
        self.default_output_dir = default_output_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

        self.title("1688 素材分类预览与选款下载工作台")
        self.geometry("1020x760")
        self.minsize(860, 620)

        # 状态记录
        self.gallery_vars: List[tk.BooleanVar] = []
        self.sku_vars: List[tk.BooleanVar] = []
        self.detail_vars: List[tk.BooleanVar] = []
        self.thumb_cache: Dict[str, ImageTk.PhotoImage] = {}
        self.is_downloading = False
        self.saved_output_dir = ""

        # 建立 UI
        self._init_ui()
        self._load_data()

        # 居中显示
        self.update_idletasks()
        w = self.winfo_width()
        h = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (w // 2)
        y = (self.winfo_screenheight() // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.transient(parent)
        self.grab_set()

    def _init_ui(self):
        # 1. 顶部商品标题与链接展示
        header_frame = ttk.Frame(self, padding=(14, 10, 14, 6))
        header_frame.pack(fill=tk.X)

        title_text = self.raw_data.get('title', '未命名商品')
        lbl_title = ttk.Label(header_frame, text=f"📦 {title_text}", font=("Helvetica", 13, "bold"), wraplength=980)
        lbl_title.pack(anchor="w")

        page_url = self.raw_data.get('pageUrl', '')
        if page_url:
            lbl_url = ttk.Label(header_frame, text=f"🔗 {page_url}", foreground="#0284c7", font=("Helvetica", 10), wraplength=980)
            lbl_url.pack(anchor="w", pady=(2, 0))

        # 2. 中间多 Tab 分类预览面板
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=14, pady=6)

        # Tab 1: 主图画廊
        self.tab_gallery = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_gallery, text="  🖼️ 主图画廊  ")
        self._build_gallery_tab()

        # Tab 2: SKU 规格色卡
        self.tab_sku = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_sku, text="  🎨 SKU 规格与色卡  ")
        self._build_sku_tab()

        # Tab 3: 商品详情图
        self.tab_detail = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_detail, text="  📋 商品详情大图  ")
        self._build_detail_tab()

        # Tab 4: 变体明细矩阵表格
        self.tab_matrix = ttk.Frame(self.notebook, padding=8)
        self.notebook.add(self.tab_matrix, text="  📊 变体明细数据表  ")
        self._build_matrix_tab()

        # 3. 底部下载配置与操作条
        bottom_frame = ttk.Frame(self, padding=(14, 8, 14, 10))
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        # 目录选择行
        dir_row = ttk.Frame(bottom_frame)
        dir_row.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(dir_row, text="保存目录:").pack(side=tk.LEFT)
        self.save_dir_var = tk.StringVar(value=self.default_output_dir)
        ent_dir = ttk.Entry(dir_row, textvariable=self.save_dir_var, font=("Helvetica", 10))
        ent_dir.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        btn_browse = ttk.Button(dir_row, text="浏览...", command=self._on_browse_dir)
        btn_browse.pack(side=tk.RIGHT)

        # 统计与操作行
        action_row = ttk.Frame(bottom_frame)
        action_row.pack(fill=tk.X)

        self.lbl_summary = ttk.Label(action_row, text="统计计算中...", font=("Helvetica", 10, "bold"), foreground="#475569")
        self.lbl_summary.pack(side=tk.LEFT)

        self.btn_open_folder = ttk.Button(action_row, text="📂 打开下载目录", state="disabled", command=self._on_open_folder)
        self.btn_open_folder.pack(side=tk.RIGHT, padx=(6, 0))

        self.btn_download = ttk.Button(action_row, text="⬇️ 开始下载选中素材", style="Accent.TButton", command=self._on_start_download)
        self.btn_download.pack(side=tk.RIGHT, padx=(6, 0))

        btn_close = ttk.Button(action_row, text="关闭", command=self.destroy)
        btn_close.pack(side=tk.RIGHT)

        # 进度条与状态展示
        self.progress_frame = ttk.Frame(bottom_frame)
        self.progress_frame.pack(fill=tk.X, pady=(6, 0))
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(fill=tk.X, side=tk.TOP)
        self.lbl_status = ttk.Label(self.progress_frame, text="准备就绪，请勾选所需素材后点击下载", font=("Helvetica", 9), foreground="#64748b")
        self.lbl_status.pack(side=tk.LEFT, pady=(2, 0))

    # =========================================================================
    # Tab 1: 主图画廊
    # =========================================================================
    def _build_gallery_tab(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self.tab_gallery)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(toolbar, text="全选", command=lambda: self._set_all_vars(self.gallery_vars, True)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="清空", command=lambda: self._set_all_vars(self.gallery_vars, False)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="仅选前 5 张", command=self._select_top5_gallery).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="反选", command=lambda: self._invert_vars(self.gallery_vars)).pack(side=tk.LEFT, padx=(0, 4))

        self.lbl_gallery_badge = ttk.Label(toolbar, text="共 0 张主图", font=("Helvetica", 9), foreground="#6b7280")
        self.lbl_gallery_badge.pack(side=tk.RIGHT)

        # 缩略图滚动容器
        self.gallery_canvas, self.gallery_inner = self._create_scrollable_area(self.tab_gallery)

    # =========================================================================
    # Tab 2: SKU 规格色卡
    # =========================================================================
    def _build_sku_tab(self):
        toolbar = ttk.Frame(self.tab_sku)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(toolbar, text="全选", command=lambda: self._set_all_vars(self.sku_vars, True)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="清空", command=lambda: self._set_all_vars(self.sku_vars, False)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="🔥 快选有效款 (库存≥50)", command=self._select_safe_stock_sku).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="反选", command=lambda: self._invert_vars(self.sku_vars)).pack(side=tk.LEFT, padx=(0, 4))

        self.lbl_sku_badge = ttk.Label(toolbar, text="共 0 款 SKU", font=("Helvetica", 9), foreground="#6b7280")
        self.lbl_sku_badge.pack(side=tk.RIGHT)

        self.sku_canvas, self.sku_inner = self._create_scrollable_area(self.tab_sku)

    # =========================================================================
    # Tab 3: 商品详情图
    # =========================================================================
    def _build_detail_tab(self):
        toolbar = ttk.Frame(self.tab_detail)
        toolbar.pack(fill=tk.X, pady=(0, 6))

        ttk.Button(toolbar, text="全选", command=lambda: self._set_all_vars(self.detail_vars, True)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="清空", command=lambda: self._set_all_vars(self.detail_vars, False)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(toolbar, text="反选", command=lambda: self._invert_vars(self.detail_vars)).pack(side=tk.LEFT, padx=(0, 4))

        self.lbl_detail_badge = ttk.Label(toolbar, text="共 0 张详情图", font=("Helvetica", 9), foreground="#6b7280")
        self.lbl_detail_badge.pack(side=tk.RIGHT)

        self.detail_canvas, self.detail_inner = self._create_scrollable_area(self.tab_detail)

    # =========================================================================
    # Tab 4: 变体明细矩阵
    # =========================================================================
    def _build_matrix_tab(self):
        cols = ("idx", "color", "size", "price", "stock", "img_name")
        self.tree_matrix = ttk.Treeview(self.tab_matrix, columns=cols, show="headings", height=16)
        self.tree_matrix.heading("idx", text="序号")
        self.tree_matrix.heading("color", text="属性1 (如颜色)")
        self.tree_matrix.heading("size", text="属性2 (如尺码/规格)")
        self.tree_matrix.heading("price", text="阶梯单价(元)")
        self.tree_matrix.heading("stock", text="当前库存")
        self.tree_matrix.heading("img_name", text="关联图片")

        self.tree_matrix.column("idx", width=50, anchor="center")
        self.tree_matrix.column("color", width=160, anchor="w")
        self.tree_matrix.column("size", width=140, anchor="w")
        self.tree_matrix.column("price", width=100, anchor="center")
        self.tree_matrix.column("stock", width=100, anchor="center")
        self.tree_matrix.column("img_name", width=220, anchor="w")

        scroll_y = ttk.Scrollbar(self.tab_matrix, orient=tk.VERTICAL, command=self.tree_matrix.yview)
        self.tree_matrix.configure(yscrollcommand=scroll_y.set)

        self.tree_matrix.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)

    # =========================================================================
    # 辅助方法：可滚动容器构建
    # =========================================================================
    def _create_scrollable_area(self, parent_tab: ttk.Frame):
        canvas = tk.Canvas(parent_tab, highlightthickness=0, bg="#f8fafc")
        scrollbar = ttk.Scrollbar(parent_tab, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)

        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def _on_canvas_configure(event):
            canvas.itemconfig(inner_id, width=event.width)

        inner.bind("<Configure>", _on_frame_configure)
        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        # 鼠标滚轮绑定
        def _on_mousewheel(event):
            if event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        return canvas, inner

    # =========================================================================
    # 数据加载与卡片渲染
    # =========================================================================
    def _load_data(self):
        gallery_list = self.raw_data.get('gallery', [])
        sku_list = self.raw_data.get('sku', [])
        detail_list = self.raw_data.get('detail', [])
        sku_matrix = self.raw_data.get('skuData', {}).get('skuMatrix', [])

        self.lbl_gallery_badge.config(text=f"共 {len(gallery_list)} 张主图")
        self.lbl_sku_badge.config(text=f"共 {len(sku_list)} 款规格色卡")
        self.lbl_detail_badge.config(text=f"共 {len(detail_list)} 张详情图")

        # 1. 渲染主图卡片 (每行 5 个)
        cols_per_row = 5
        for i, item in enumerate(gallery_list):
            var = tk.BooleanVar(value=True)
            self.gallery_vars.append(var)
            var.trace_add("write", lambda *args: self._update_summary())

            r, c = divmod(i, cols_per_row)
            card = self._create_image_card(self.gallery_inner, item, var, f"主图 {i+1}", i)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")

        # 2. 渲染 SKU 卡片 (每行 4 个)
        for i, item in enumerate(sku_list):
            var = tk.BooleanVar(value=True)
            self.sku_vars.append(var)
            var.trace_add("write", lambda *args: self._update_summary())

            # 寻找该 SKU 对应的库存或价格信息
            name = item.get('name', f'规格 {i+1}')
            r, c = divmod(i, 4)
            card = self._create_sku_card(self.sku_inner, item, var, name, i)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")

        # 3. 渲染详情图卡片 (每行 4 个)
        for i, item in enumerate(detail_list):
            var = tk.BooleanVar(value=True)
            self.detail_vars.append(var)
            var.trace_add("write", lambda *args: self._update_summary())

            r, c = divmod(i, 4)
            card = self._create_image_card(self.detail_inner, item, var, f"详情 {i+1}", i)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="n")

        # 4. 填充变体表格
        for i, row in enumerate(sku_matrix):
            attrs = row.get('specAttributes', '').split('&')
            val1 = attrs[0] if len(attrs) > 0 else ''
            val2 = attrs[1] if len(attrs) > 1 else ''
            price = row.get('price', '-')
            stock = row.get('stock', '-')
            img_name = row.get('skuImageName', '-')
            self.tree_matrix.insert("", tk.END, values=(i+1, val1, val2, price, stock, img_name))

        self._update_summary()

    def _create_image_card(self, parent: ttk.Frame, item: Dict[str, str], var: tk.BooleanVar, label_text: str, index: int) -> ttk.Frame:
        card = ttk.Frame(parent, relief="groove", borderwidth=1, padding=4)

        # 顶部复选框 + 序号
        top_bar = ttk.Frame(card)
        top_bar.pack(fill=tk.X)
        cb = ttk.Checkbutton(top_bar, text=label_text, variable=var)
        cb.pack(side=tk.LEFT)

        # 缩略图图片 Label
        lbl_img = tk.Label(card, text="加载中...", width=14, height=6, bg="#e2e8f0", cursor="hand2")
        lbl_img.pack(pady=4)

        url = item.get('url', '')
        if url:
            lbl_img.bind("<Button-1>", lambda e, u=url, t=label_text: self._show_lightbox(u, t))
            threading.Thread(target=self._async_fetch_thumb, args=(url, lbl_img, (110, 110)), daemon=True).start()

        return card

    def _create_sku_card(self, parent: ttk.Frame, item: Dict[str, str], var: tk.BooleanVar, title_text: str, index: int) -> ttk.Frame:
        card = ttk.Frame(parent, relief="groove", borderwidth=1, padding=6)

        # 顶部复选框
        cb = ttk.Checkbutton(card, text=title_text[:14] + ("..." if len(title_text) > 14 else ""), variable=var)
        cb.pack(anchor="w")

        # 图片区域
        lbl_img = tk.Label(card, text="加载中...", width=16, height=6, bg="#e2e8f0", cursor="hand2")
        lbl_img.pack(pady=4)

        url = item.get('url', '')
        if url:
            lbl_img.bind("<Button-1>", lambda e, u=url, t=title_text: self._show_lightbox(u, t))
            threading.Thread(target=self._async_fetch_thumb, args=(url, lbl_img, (110, 110)), daemon=True).start()

        # 底部规格与价格说明
        lbl_sub = ttk.Label(card, text=title_text, font=("Helvetica", 9), wraplength=130)
        lbl_sub.pack(anchor="w")

        return card

    def _async_fetch_thumb(self, url: str, label: tk.Label, size=(110, 110)):
        if url.startswith('//'):
            url = 'https:' + url
        try:
            r = requests.get(url, timeout=8)
            if r.status_code == 200:
                img_data = Image.open(io.BytesIO(r.content))
                img_data.thumbnail(size, Image.LANCZOS)
                photo = ImageTk.PhotoImage(img_data)
                self.thumb_cache[url] = photo

                def _update():
                    if label.winfo_exists():
                        label.config(image=photo, text="", width=size[0], height=size[1])
                self.after(0, _update)
        except Exception:
            def _fail():
                if label.winfo_exists():
                    label.config(text="加载失败", bg="#fecaca")
            self.after(0, _fail)

    # =========================================================================
    # 交互控制：全选/反选/筛选
    # =========================================================================
    def _set_all_vars(self, vars_list: List[tk.BooleanVar], value: bool):
        for v in vars_list:
            v.set(value)

    def _invert_vars(self, vars_list: List[tk.BooleanVar]):
        for v in vars_list:
            v.set(not v.get())

    def _select_top5_gallery(self):
        for i, v in enumerate(self.gallery_vars):
            v.set(i < 5)

    def _select_safe_stock_sku(self):
        """仅勾选库存 >= 50 的 SKU 款式"""
        sku_list = self.raw_data.get('sku', [])
        sku_matrix = self.raw_data.get('skuData', {}).get('skuMatrix', [])

        # 建立色卡名称到最大库存的映射
        stock_map = {}
        for row in sku_matrix:
            name = row.get('skuImageName', '') or row.get('specAttributes', '')
            try:
                stk = int(row.get('stock', 0))
            except Exception:
                stk = 0
            for k in stock_map.keys() if stock_map else []:
                if k in name:
                    stock_map[k] = max(stock_map[k], stk)
            stock_map[name] = max(stock_map.get(name, 0), stk)

        for i, (v, item) in enumerate(zip(self.sku_vars, sku_list)):
            name = item.get('name', '')
            # 判断对应库存
            stk = 100
            for k, s in stock_map.items():
                if name in k or k in name:
                    stk = s
                    break
            v.set(stk >= 50)

    def _update_summary(self):
        sel_g = sum(1 for v in self.gallery_vars if v.get())
        tot_g = len(self.gallery_vars)

        sel_s = sum(1 for v in self.sku_vars if v.get())
        tot_s = len(self.sku_vars)

        sel_d = sum(1 for v in self.detail_vars if v.get())
        tot_d = len(self.detail_vars)

        self.lbl_summary.config(
            text=f"📊 已选择: 主图 {sel_g}/{tot_g} 张 | SKU 色卡 {sel_s}/{tot_s} 款 | 详情图 {sel_d}/{tot_d} 张"
        )

    def _show_lightbox(self, url: str, title: str):
        """点击缩略图放大查看高清大图"""
        top = tk.Toplevel(self)
        top.title(f"大图预览 - {title}")
        top.geometry("700x700")

        lbl_loading = ttk.Label(top, text="正在加载高清原图...", font=("Helvetica", 12))
        lbl_loading.pack(expand=True)

        def _fetch_large():
            if url.startswith('//'):
                real_url = 'https:' + url
            else:
                real_url = url
            try:
                r = requests.get(real_url, timeout=10)
                if r.status_code == 200:
                    img_data = Image.open(io.BytesIO(r.content))
                    # 适度缩放不超过 680x680
                    img_data.thumbnail((680, 680), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img_data)

                    def _show():
                        lbl_loading.destroy()
                        lbl_large = tk.Label(top, image=photo)
                        lbl_large.image = photo
                        lbl_large.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
                    self.after(0, _show)
            except Exception as e:
                def _err():
                    lbl_loading.config(text=f"加载原图失败: {str(e)}")
                self.after(0, _err)

        threading.Thread(target=_fetch_large, daemon=True).start()

    # =========================================================================
    # 下载与生成逻辑
    # =========================================================================
    def _on_browse_dir(self):
        path = filedialog.askdirectory(initialdir=self.save_dir_var.get())
        if path:
            self.save_dir_var.set(path)

    def _on_start_download(self):
        if self.is_downloading:
            return

        sel_g = [i for i, v in enumerate(self.gallery_vars) if v.get()]
        sel_s = [i for i, v in enumerate(self.sku_vars) if v.get()]
        sel_d = [i for i, v in enumerate(self.detail_vars) if v.get()]

        if not sel_g and not sel_s and not sel_d:
            messagebox.showwarning("提示", "您尚未勾选任何需要下载的图片素材！")
            return

        base_dir = self.save_dir_var.get().strip()
        if not os.path.exists(base_dir):
            try:
                os.makedirs(base_dir, exist_ok=True)
            except Exception:
                messagebox.showerror("错误", "指定的保存路径不存在且无法创建！")
                return

        selection = {
            "gallery_indices": sel_g,
            "sku_indices": sel_s,
            "detail_indices": sel_d,
            "sku_matrix_indices": list(range(len(self.raw_data.get('skuData', {}).get('skuMatrix', []))))
        }

        self.is_downloading = True
        self.btn_download.config(state="disabled")
        self.lbl_status.config(text="正在开始多线程并发下载...", foreground="#0284c7")

        def _worker():
            def _progress(curr, total, desc):
                pct = int((curr / total) * 100) if total > 0 else 0
                self.after(0, lambda: self._update_download_progress(curr, total, pct, desc))

            ok, out_dir, stats = self.scraper.download_selected_assets(
                self.raw_data, selection, base_dir, progress_cb=_progress
            )

            def _done():
                self.is_downloading = False
                self.btn_download.config(state="normal")
                if ok:
                    self.saved_output_dir = out_dir
                    self.btn_open_folder.config(state="normal")
                    self.lbl_status.config(
                        text=f"✅ 下载完成！已保存至 {out_dir} (主图 {stats.get('gallery',0)} 张, SKU图 {stats.get('sku_images',0)} 张, 详情图 {stats.get('detail',0)} 张)",
                        foreground="#16a34a"
                    )
                    messagebox.showinfo("下载完成", f"🎉 素材与配置文件已成功导出至：\n{out_dir}\n\n已自动生成 sku_data.txt 配置文件！")
                else:
                    self.lbl_status.config(text=f"❌ 下载过程出错: {out_dir}", foreground="#dc2626")
                    messagebox.showerror("下载失败", f"下载出现错误: {out_dir}")

            self.after(0, _done)

        threading.Thread(target=_worker, daemon=True).start()

    def _update_download_progress(self, curr: int, total: int, pct: int, desc: str):
        self.progress_bar.config(value=pct)
        self.lbl_status.config(text=f"正在并发下载 [{curr}/{total}] ({pct}%): {desc}")

    def _on_open_folder(self):
        """在系统资源管理器/Finder中打开文件夹"""
        target = self.saved_output_dir or self.save_dir_var.get()
        if os.path.exists(target):
            if sys.platform == "darwin":
                subprocess.Popen(["open", target])
            elif sys.platform == "win32":
                os.startfile(target)
            else:
                subprocess.Popen(["xdg-open", target])
