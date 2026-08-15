"""
1688 货源平台数据采集与素材按需下载模块
"""
import os
import sys
import time
import json
import requests
import threading
from typing import Optional, Dict, Any, List, Tuple, Callable
from playwright.sync_api import Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_CACHED_COLLECTOR_JS = None
_CACHED_CONTENT_JS = None

def _get_scraper_scripts():
    global _CACHED_COLLECTOR_JS, _CACHED_CONTENT_JS
    if _CACHED_COLLECTOR_JS is None or _CACHED_CONTENT_JS is None:
        collector_js_path = "/Users/gx/Desktop/mypro/1688-Image-Downloader/1688_sku_collector.js"
        content_js_path = "/Users/gx/Desktop/mypro/1688-Image-Downloader/content.js"
        if os.path.exists(collector_js_path):
            with open(collector_js_path, 'r', encoding='utf-8') as f:
                _CACHED_COLLECTOR_JS = f.read()
        if os.path.exists(content_js_path):
            with open(content_js_path, 'r', encoding='utf-8') as f:
                _CACHED_CONTENT_JS = f.read()
    return _CACHED_COLLECTOR_JS, _CACHED_CONTENT_JS


class Scraper1688:
    """1688 数据采集与素材下载器"""

    def __init__(self, page: Page, log_fn: Optional[Callable[[str, str], None]] = None):
        self.page = page
        self.log_fn = log_fn or self._default_log

    def _default_log(self, msg: str, level: str = "info"):
        prefix = "ℹ️" if level == "info" else ("✅" if level == "success" else ("⚠️" if level == "warn" else "❌"))
        print(f"[{time.strftime('%H:%M:%S')}] {prefix} {msg}")

    def log(self, msg: str, level: str = "info"):
        if self.log_fn:
            self.log_fn(msg, level)

    def is_1688_page(self) -> bool:
        """检查当前页面是否是 1688 页面"""
        try:
            return '1688.com' in self.page.url
        except Exception:
            return False

    def is_1688_detail_page(self) -> bool:
        """检查当前页面是否是 1688 具体商品详情页"""
        try:
            url = self.page.url
            return 'detail.1688.com' in url or '/offer/' in url
        except Exception:
            return False

    def is_logged_in(self) -> bool:
        """检查当前 1688 页面是否处于登录状态"""
        try:
            return self.page.locator(".has-login, .login-user-name, [class*='login-user'], .member-info").count() > 0
        except Exception:
            return False

    def extract_data_only(self) -> Optional[Dict[str, Any]]:
        """
        核心方法 1：仅从 1688 页面中提取完整结构化数据（主图、SKU色卡、详情图、变体矩阵）
        不写磁盘、不提前下载图片，秒级返回纯内存数据结构供预览与筛选。
        """
        if not self.is_1688_page():
            self.log("当前选中的标签页不是 1688 页面！", "warn")
            return None

        if not self.is_1688_detail_page():
            self.log("⚠️ 当前页面是 1688 首页或列表页，请先在浏览器中打开具体的【商品详情页】！", "warn")
            return None

        collector_js, content_js = _get_scraper_scripts()

        if not collector_js or not content_js:
            self.log("未找到 1688-Image-Downloader 脚本，请确保路径配置正确！", "error")
            return None

        try:
            self.log("正在解析 1688 页面商品与变体数据...", "info")

            # 1. 注入模拟 chrome extension runtime，避免调用报错
            mock_chrome_js = """
            if (typeof window.chrome === 'undefined') {
                window.chrome = {};
            }
            if (typeof window.chrome.runtime === 'undefined') {
                window.chrome.runtime = {
                    onMessage: { addListener: function() {} },
                    sendMessage: function() {}
                };
            }
            """
            self.page.evaluate(mock_chrome_js)

            # 2. 注入 SkuCollector1688 全局对象（解决 1688 页面上 AMD define.amd 导致 UMD 未暴露到 window 的问题）
            inject_collector_js = f"""
            (() => {{
                const _origDef = window.define;
                const _origMod = window.module;
                try {{
                    window.define = undefined;
                    window.module = undefined;
                    {collector_js}
                }} finally {{
                    window.define = _origDef;
                    window.module = _origMod;
                }}
            }})();
            """
            self.page.evaluate(inject_collector_js)

            # 3. 执行 content.js 获取全量解析结果
            result = self.page.evaluate(content_js)

            if not result:
                self.log("未能成功解析出商品数据，请确认页面已完全加载！", "error")
                return None

            # 4. 标题兜底增强：若未能通过选择器提取到标题，使用页面原生 Title 或 DOM 标签
            title = (result.get('title') or '').strip()
            if not title:
                try:
                    page_title = self.page.title() or ''
                    clean_title = page_title.split('-')[0].replace('【阿里巴巴】', '').replace('- 阿里巴巴', '').strip()
                    if clean_title:
                        title = clean_title
                    else:
                        title = self.page.evaluate("""() => {
                            const el = document.querySelector('h1, .title-text, .od-title, [class*="product-title"]');
                            return el ? el.innerText.trim() : '';
                        }""")
                except Exception:
                    pass

            if not title:
                title = "1688商品_" + str(int(time.time()))

            result['title'] = title

            gallery_count = len(result.get('gallery', []))
            sku_count = len(result.get('sku', []))
            detail_count = len(result.get('detail', []))
            sku_matrix_count = len(result.get('skuData', {}).get('skuMatrix', []))

            self.log(f"✅ 1688 数据解析成功！【{title[:25]}...】", "success")
            self.log(f"📊 提取素材概览: 主图 {gallery_count} 张 | SKU色卡 {sku_count} 款 | 详情图 {detail_count} 张 | 变体明细 {sku_matrix_count} 行", "info")

            return result

        except Exception as e:
            self.log(f"解析 1688 页面数据异常: {str(e)}", "error")
            return None

    def download_selected_assets(
        self,
        raw_data: Dict[str, Any],
        selection: Dict[str, Any],
        output_base_dir: str,
        progress_cb: Optional[Callable[[int, int, str], None]] = None
    ) -> Tuple[bool, str, Dict[str, int]]:
        """
        核心方法 2：根据用户在预览面板中勾选的列表，按需多线程并发下载图片并生成配置文件。
        selection 结构:
        {
            "gallery_indices": [0, 1, 2, ...],
            "sku_indices": [0, 2, 5, ...], # 选中的 sku 色卡索引
            "detail_indices": [0, 1, ...],
            "sku_matrix_indices": [0, 1, 2, ...] # 选中的具体 SKU 变体行索引
        }
        """
        try:
            title = raw_data.get('title', '1688商品')
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
            if not safe_title:
                safe_title = f"goods_{int(time.time())}"

            save_dir = os.path.join(output_base_dir, f"1688_{safe_title}")
            os.makedirs(save_dir, exist_ok=True)

            main_dir = os.path.join(save_dir, "0gallery")
            detail_dir = os.path.join(save_dir, "1detail")
            sku_dir = os.path.join(save_dir, "2sku")

            os.makedirs(main_dir, exist_ok=True)
            os.makedirs(detail_dir, exist_ok=True)
            os.makedirs(sku_dir, exist_ok=True)

            # 保存选中的 raw_data 方便溯源
            with open(os.path.join(save_dir, "raw_data.json"), 'w', encoding='utf-8') as f:
                json.dump(raw_data, f, ensure_ascii=False, indent=2)

            # 收集所有待下载的任务
            download_tasks = []  # List of (url, target_path, desc)

            # 1. 选中的主图
            sel_gallery_idx = set(selection.get("gallery_indices", []))
            all_gallery = raw_data.get('gallery', [])
            saved_gallery_files = []
            for i, img in enumerate(all_gallery):
                if i in sel_gallery_idx:
                    url = img.get('url')
                    if url:
                        filename = f"main_{len(saved_gallery_files)+1}.jpg"
                        target_p = os.path.join(main_dir, filename)
                        saved_gallery_files.append(filename)
                        download_tasks.append((url, target_p, f"主图 {filename}"))

            # 2. 选中的详情图
            sel_detail_idx = set(selection.get("detail_indices", []))
            all_detail = raw_data.get('detail', [])
            saved_detail_files = []
            for i, img in enumerate(all_detail):
                if i in sel_detail_idx:
                    url = img.get('url')
                    if url:
                        filename = f"detail_{len(saved_detail_files)+1}.jpg"
                        target_p = os.path.join(detail_dir, filename)
                        saved_detail_files.append(filename)
                        download_tasks.append((url, target_p, f"详情图 {filename}"))

            # 3. 选中的 SKU 色卡图
            sel_sku_idx = set(selection.get("sku_indices", []))
            all_sku = raw_data.get('sku', [])
            for i, img in enumerate(all_sku):
                if i in sel_sku_idx:
                    url = img.get('url')
                    if url:
                        name = img.get('name', f"sku_{i+1}")
                        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
                        target_p = os.path.join(sku_dir, f"{safe_name}.jpg")
                        download_tasks.append((url, target_p, f"SKU图 {safe_name}"))

            # 多线程下载执行
            total_tasks = len(download_tasks)
            completed = 0
            lock = threading.Lock()

            def _download_one(task):
                nonlocal completed
                url, path, desc = task
                if url.startswith('//'):
                    url = 'https:' + url
                try:
                    r = requests.get(url, timeout=12)
                    if r.status_code == 200 and len(r.content) > 100:
                        with open(path, 'wb') as f:
                            f.write(r.content)
                except Exception:
                    pass
                with lock:
                    completed += 1
                    if progress_cb:
                        progress_cb(completed, total_tasks, desc)

            threads = []
            max_workers = 10
            for i in range(0, total_tasks, max_workers):
                batch = download_tasks[i:i + max_workers]
                batch_threads = []
                for task in batch:
                    t = threading.Thread(target=_download_one, args=(task,))
                    t.start()
                    batch_threads.append(t)
                for t in batch_threads:
                    t.join()

            # 4. 生成匹配选中 SKU 的 sku_data.txt 配置文件
            sku_data = raw_data.get('skuData', {})
            sku_matrix = sku_data.get('skuMatrix', [])
            sku_props = sku_data.get('skuProps', [])

            sel_matrix_idx = set(selection.get("sku_matrix_indices", list(range(len(sku_matrix)))))

            dim1_name = sku_props[0]['prop'] if len(sku_props) > 0 else "属性1"
            dim2_name = sku_props[1]['prop'] if len(sku_props) > 1 else "属性2"

            txt_lines = []
            txt_lines.append(save_dir)
            txt_lines.append(safe_title)
            main_img_ref = f"0gallery/{saved_gallery_files[0]}" if saved_gallery_files else "0gallery/main_1.jpg"
            txt_lines.append(main_img_ref)
            txt_lines.append("1detail")
            txt_lines.append("2sku")

            txt_lines.append(f'"sku主图"-"{dim1_name}"-"{dim2_name}"-"产品编码"-"价格"-"库存"-"物品状况"-"平台SKU"-"促销价格"-"促销时间"')

            valid_sku_rows = 0
            for i, sku_item in enumerate(sku_matrix):
                if i not in sel_matrix_idx:
                    continue

                attrs = sku_item.get('specAttributes', '').split('&')
                val1 = attrs[0] if len(attrs) > 0 else ''
                val2 = attrs[1] if len(attrs) > 1 else ''

                price = sku_item.get('price', '')
                stock = sku_item.get('stock', '100')
                sku_img_name = sku_item.get('skuImageName', '')

                img_file = ""
                if sku_img_name:
                    img_file = "".join(c for c in sku_img_name if c.isalnum() or c in (' ', '-', '_')).strip() + ".jpg"
                elif val1:
                    img_file = "".join(c for c in val1 if c.isalnum() or c in (' ', '-', '_')).strip() + ".jpg"

                line = f'"{img_file}"-"{val1}"-"{val2}"-"CODE{valid_sku_rows+1:03d}"-"{price}"-"{stock}"-"新"-"SKU-{valid_sku_rows+1}"-""-""'
                txt_lines.append(line)
                valid_sku_rows += 1

            txt_path = os.path.join(save_dir, "sku_data.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(txt_lines))

            stats = {
                "gallery": len(saved_gallery_files),
                "detail": len(saved_detail_files),
                "sku_images": len(sel_sku_idx),
                "sku_rows": valid_sku_rows
            }
            return True, save_dir, stats

        except Exception as e:
            return False, str(e), {}
