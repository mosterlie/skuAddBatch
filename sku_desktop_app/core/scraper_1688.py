"""
1688 货源平台数据采集与会话管理模块
"""
import os
import sys
import time
import json
import requests
import threading
from typing import Optional, Dict, Any, List
from playwright.sync_api import Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config


class Scraper1688:
    """1688 数据采集与状态检查器"""

    def __init__(self, page: Page, log_fn=None):
        self.page = page
        self.log_fn = log_fn or print

    def log(self, msg: str, level: str = "info"):
        if self.log_fn:
            self.log_fn(msg, level)

    def is_1688_page(self) -> bool:
        """检查当前页面是否是 1688 页面"""
        return '1688.com' in self.page.url

    def extract_and_download(self, base_workspace_dir: str):
        """
        核心方法：注入 1688-Image-Downloader 脚本提取数据，下载图片，并生成 sku.txt
        """
        self.log("开始采集 1688 页面数据...", "info")
        collector_js_path = "/Users/gx/Desktop/mypro/1688-Image-Downloader/1688_sku_collector.js"
        content_js_path = "/Users/gx/Desktop/mypro/1688-Image-Downloader/content.js"
        
        if not os.path.exists(collector_js_path) or not os.path.exists(content_js_path):
            self.log("未找到 1688-Image-Downloader 脚本，请确保路径正确！", "error")
            return
            
        with open(collector_js_path, 'r', encoding='utf-8') as f:
            collector_js = f.read()
        with open(content_js_path, 'r', encoding='utf-8') as f:
            content_js = f.read()

        try:
            # 1. 注入 SkuCollector1688 全局对象
            self.page.evaluate(collector_js)
            time.sleep(0.5)
            
            # 为了防止原插件内容脚本调用 chrome extension 专属 api 报错，先注入一个假的 chrome 对象
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
            
            # 2. 运行 content_js 获取解析结果
            self.log("正在解析 SKU 和图片数据...", "info")
            result = self.page.evaluate(content_js)
            
            if not result or not result.get('title'):
                self.log("未能成功解析出商品数据！", "error")
                return
                
            title = result['title']
            safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:30]
            
            # 3. 创建目录结构
            save_dir = os.path.join(base_workspace_dir, f"1688_{safe_title}")
            os.makedirs(save_dir, exist_ok=True)
            
            main_dir = os.path.join(save_dir, "0gallery")
            detail_dir = os.path.join(save_dir, "1detail")
            sku_dir = os.path.join(save_dir, "2sku")
            
            os.makedirs(main_dir, exist_ok=True)
            os.makedirs(detail_dir, exist_ok=True)
            os.makedirs(sku_dir, exist_ok=True)
            
            # 保存原始 JSON 方便调试
            with open(os.path.join(save_dir, "raw_data.json"), 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
                
            # 4. 异步下载图片
            self.log(f"解析成功！开始下载图片至: {save_dir}", "success")
            
            def download_image(url, save_path):
                if not url: return
                if url.startswith('//'): url = 'https:' + url
                try:
                    r = requests.get(url, timeout=10)
                    if r.status_code == 200:
                        with open(save_path, 'wb') as f:
                            f.write(r.content)
                except Exception as e:
                    pass

            threads = []
            
            # 下载主图
            for i, img in enumerate(result.get('gallery', [])):
                url = img.get('url')
                if url:
                    t = threading.Thread(target=download_image, args=(url, os.path.join(main_dir, f"main_{i+1}.jpg")))
                    threads.append(t)
                    t.start()
                    
            # 下载详情图
            for i, img in enumerate(result.get('detail', [])):
                url = img.get('url')
                if url:
                    t = threading.Thread(target=download_image, args=(url, os.path.join(detail_dir, f"detail_{i+1}.jpg")))
                    threads.append(t)
                    t.start()
                    
            # 下载 SKU 图
            sku_list = result.get('sku', [])
            for i, img in enumerate(sku_list):
                url = img.get('url')
                if url:
                    # 获取该 sku 图对应的颜色名
                    name = img.get('name', f"sku_{i+1}")
                    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
                    t = threading.Thread(target=download_image, args=(url, os.path.join(sku_dir, f"{safe_name}.jpg")))
                    threads.append(t)
                    t.start()
                    
            for t in threads:
                t.join()
                
            self.log(f"成功下载 {len(threads)} 张图片！", "success")
            
            # 5. 生成 skuAddBatch 的配置文件 sku.txt
            self.log("正在生成适配器所需的 SKU 数据文件...", "info")
            sku_data = result.get('skuData', {})
            sku_matrix = sku_data.get('skuMatrix', [])
            sku_props = sku_data.get('skuProps', [])
            
            # 识别主要维度名称，比如 "颜色", "尺码"
            dim1_name = sku_props[0]['prop'] if len(sku_props) > 0 else "属性1"
            dim2_name = sku_props[1]['prop'] if len(sku_props) > 1 else "属性2"
            
            txt_lines = []
            txt_lines.append(save_dir)
            txt_lines.append(safe_title)
            # 主图和详情图和SKU图的相对目录名
            txt_lines.append("0gallery/main_1.jpg") # 随便指定一个主图名作为示例
            txt_lines.append("1detail")
            txt_lines.append("2sku")
            
            # 表头
            txt_lines.append(f'"sku主图"-"{dim1_name}"-"{dim2_name}"-"产品编码"-"价格"-"库存"-"物品状况"-"平台SKU"-"促销价格"-"促销时间"')
            
            # 填充表格行
            for i, sku_item in enumerate(sku_matrix):
                # sku_item.specAttributes: "红色&XL"
                attrs = sku_item.get('specAttributes', '').split('&')
                val1 = attrs[0] if len(attrs) > 0 else ''
                val2 = attrs[1] if len(attrs) > 1 else ''
                
                price = sku_item.get('price', '')
                stock = sku_item.get('stock', '100')
                sku_img_url = sku_item.get('skuImageUrl', '')
                sku_img_name = sku_item.get('skuImageName', '')
                
                # 对应的文件名
                img_file = ""
                if sku_img_name:
                    img_file = "".join(c for c in sku_img_name if c.isalnum() or c in (' ', '-', '_')).strip() + ".jpg"
                elif val1:
                    img_file = "".join(c for c in val1 if c.isalnum() or c in (' ', '-', '_')).strip() + ".jpg"
                    
                line = f'"{img_file}"-"{val1}"-"{val2}"-"CODE{i+1:03d}"-"{price}"-"{stock}"-"新"-"SKU-{i+1}"-""-""'
                txt_lines.append(line)
                
            txt_path = os.path.join(save_dir, "sku_data.txt")
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("\\n".join(txt_lines))
                
            self.log(f"✅ 1688 数据提取完毕！配置文件已保存至: {txt_path}", "success")
            
        except Exception as e:
            self.log(f"采集过程出现异常: {str(e)}", "error")
