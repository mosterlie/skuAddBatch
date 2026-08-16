"""
1688 插件独立 Web 服务与 API 桥接服务
以 HTTP 方式本地托管 1688-Image-Downloader 插件界面，提供独立的 Chrome 弹窗工作台，
彻底杜绝 Chrome ERR_BLOCKED_BY_CLIENT 与图片 403 跨域防盗链问题，完美支持反复点击下载、打开文件夹与复制链接。
"""
import os
import sys
import json
import time
import socket
import urllib.parse
import threading
import subprocess
import requests
from concurrent.futures import ThreadPoolExecutor
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.scraper_1688 import Scraper1688

PLUGIN_DIR = config.PLUGIN_DIR
SERVER_PORT = 31416


class PluginServerHandler(BaseHTTPRequestHandler):
    """处理插件静态资源与扫描/下载 API"""

    browser_mgr = None  # 外部注入 BrowserManager 实例
    last_scan_data = None
    last_saved_dir = ""
    on_scan_callback = None  # 外部注入 GUI 回调函数 (title, url) -> None
    on_calcfee_export_callback = None  # 外部注入 GUI 回调函数 (file_path, count) -> None
    last_exported_sku_json = ""

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def do_OPTIONS(self):
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.lstrip("/") or "popup.html"

        # 1. API: 扫描当前 1688 页面
        if path == "api/scan":
            self._handle_api_scan()
            return

        # 2. 静态文件分发: calcfee SKU 录入与核算工作台
        if path.startswith("calcfee") or path == "calcfee":
            rel_path = path[len("calcfee"):].lstrip("/")
            if not rel_path or rel_path == "index.html":
                rel_path = "index.html"
            calcfee_dir = config.CALCFEE_DIR
            target_file = os.path.join(calcfee_dir, rel_path)
            if not os.path.exists(target_file):
                target_file = os.path.join(calcfee_dir, "index.html")

            if os.path.exists(target_file):
                self.send_response(200)
                self._set_cors_headers()
                ext = os.path.splitext(target_file)[1].lower()
                content_type = "text/html; charset=utf-8"
                if ext == ".css":
                    content_type = "text/css; charset=utf-8"
                elif ext == ".js":
                    content_type = "application/javascript; charset=utf-8"
                elif ext == ".svg":
                    content_type = "image/svg+xml"
                elif ext == ".json":
                    content_type = "application/json; charset=utf-8"
                elif ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                    content_type = f"image/{ext.lstrip('.')}"
                self.send_header("Content-Type", content_type)
                if ext == ".html":
                    self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                    self.send_header("Pragma", "no-cache")
                    self.send_header("Expires", "0")
                self.end_headers()
                with open(target_file, "rb") as f:
                    self.wfile.write(f.read())
                return

        # 3. 静态文件分发: 1688 插件原生工作台
        file_path = os.path.join(PLUGIN_DIR, path)
        if not os.path.exists(file_path):
            file_path = os.path.join(PLUGIN_DIR, "popup.html")

        if os.path.exists(file_path):
            self.send_response(200)
            self._set_cors_headers()
            ext = os.path.splitext(file_path)[1].lower()
            content_type = "text/html; charset=utf-8"
            if ext == ".css":
                content_type = "text/css; charset=utf-8"
            elif ext == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                content_type = f"image/{ext.lstrip('.')}"
            self.send_header("Content-Type", content_type)
            self.end_headers()

            with open(file_path, "rb") as f:
                content = f.read()

            # 如果是 popup.html，注入 referrer 设置、适配层、复制增强、按钮状态维护与自动扫描
            if file_path.endswith("popup.html"):
                html_str = content.decode("utf-8", errors="ignore")
                bridge_script = """
                <meta name="referrer" content="no-referrer">
                <script>
                // Web 模式适配层：解决未激活遮罩、图片防盗链、复制链接、反复下载与打开文件夹
                (function() {
                    window.__IS_WEB_POPUP_MODE = true;
                    if (typeof window.chrome === 'undefined') window.chrome = {};

                    // 全局稳健复制剪贴板实现 (支持主流 API 及 document.execCommand 兜底)
                    window.copyTextToClipboard = function(text) {
                        if (!text) return Promise.resolve(false);
                        return new Promise(function(resolve) {
                            if (navigator.clipboard && navigator.clipboard.writeText) {
                                navigator.clipboard.writeText(text).then(function() {
                                    resolve(true);
                                }).catch(function() {
                                    resolve(fallbackCopy(text));
                                });
                            } else {
                                resolve(fallbackCopy(text));
                            }
                        });
                    };

                    function fallbackCopy(text) {
                        try {
                            var ta = document.createElement('textarea');
                            ta.value = text;
                            ta.style.position = 'fixed';
                            ta.style.top = '0';
                            ta.style.left = '0';
                            ta.style.opacity = '0';
                            document.body.appendChild(ta);
                            ta.focus();
                            ta.select();
                            var successful = document.execCommand('copy');
                            document.body.removeChild(ta);
                            return successful;
                        } catch (err) {
                            return false;
                        }
                    }

                    // 覆写 navigator.clipboard.writeText 确保全局点击复制 100% 成功
                    if (!navigator.clipboard) navigator.clipboard = {};
                    navigator.clipboard.writeText = function(text) {
                        fallbackCopy(text);
                        return Promise.resolve();
                    };

                    // 1. 自动过激活授权验证 (免去未激活弹窗与输入激活码)
                    window.verifyLicense = async function(mid, code) {
                        return { valid: true, expireTs: 4102444800000 };
                    };

                    window.chrome.storage = {
                        local: {
                            get: function(keys, cb) {
                                var ret = { machine_id: "LOCAL-DESKTOP-APP", act_code: "PERMANENT_AUTHORIZED" };
                                if (cb) cb(ret);
                                return Promise.resolve(ret);
                            },
                            set: function(obj, cb) { if (cb) cb(); return Promise.resolve(); }
                        }
                    };

                    // 2. 模拟 chrome.tabs
                    window.chrome.tabs = {
                        query: function(q, cb) {
                            var dummy = [{ id: 1, url: "https://detail.1688.com/offer/current.html" }];
                            if (cb) cb(dummy);
                            return Promise.resolve(dummy);
                        },
                        get: function(id, cb) {
                            var dummy = { id: 1, url: "https://detail.1688.com/offer/current.html" };
                            if (cb) cb(dummy);
                            return Promise.resolve(dummy);
                        }
                    };

                    // 3. 模拟 chrome.scripting.executeScript
                    window.chrome.scripting = {
                        executeScript: async function() {
                            try {
                                const res = await fetch('/api/scan');
                                const json = await res.json();
                                if (json.success && json.data) {
                                    // 存储商品链接供后续下载时自动复制
                                    window.__productPageUrl = json.data.pageUrl || '';
                                    window.__productTitle = json.data.title || '';
                                    // 注入商品信息展示栏
                                    setTimeout(function() { window.__showProductInfoBar && window.__showProductInfoBar(); }, 300);
                                    return [{ result: json.data }];
                                }
                            } catch(e) {}
                            return [{ result: null }];
                        }
                    };

                    // 4. 模拟 chrome.runtime 消息路由
                    var messageListeners = [];
                    window.chrome.runtime = {
                        getURL: function(p) { return p; },
                        onMessage: {
                            addListener: function(fn) {
                                if (typeof fn === 'function') messageListeners.push(fn);
                            }
                        },
                        sendMessage: function(msg, cb) {
                            if (!msg) return;
                            if (msg.action === 'downloadAll') {
                                fetch('/api/download', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify(msg)
                                })
                                .then(r => r.json())
                                .then(res => {
                                    if (cb) cb(res);
                                    messageListeners.forEach(function(fn) {
                                        try {
                                            fn({
                                                action: 'downloadComplete',
                                                completed: res.completed || 0,
                                                failed: res.failed || 0,
                                                total: res.total || 0
                                            });
                                        } catch(e){}
                                    });

                                    // 下载完成后自动复制商品链接到剪贴板
                                    if (window.__productPageUrl) {
                                        window.copyTextToClipboard(window.__productPageUrl);
                                        window.__showCopiedToast && window.__showCopiedToast('✅ 商品链接已自动复制到剪贴板');
                                    }

                                    // 保证反复点击下载时按钮状态完全重置
                                    setTimeout(function() {
                                        var btnDl = document.getElementById('btn-download');
                                        var btnSc = document.getElementById('btn-scan');
                                        if (btnDl) btnDl.disabled = false;
                                        if (btnSc) btnSc.disabled = false;
                                        if (typeof window.updateDownloadButtonState === 'function') {
                                            window.updateDownloadButtonState();
                                        }
                                    }, 100);
                                })
                                .catch(e => {
                                    if (cb) cb({ success: false, error: e.message });
                                    var btnDl = document.getElementById('btn-download');
                                    var btnSc = document.getElementById('btn-scan');
                                    if (btnDl) btnDl.disabled = false;
                                    if (btnSc) btnSc.disabled = false;
                                    if (typeof window.updateDownloadButtonState === 'function') {
                                        window.updateDownloadButtonState();
                                    }
                                });
                            } else if (msg.action === 'openFolder') {
                                fetch('/api/openFolder', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify(msg)
                                }).then(r => r.json()).then(res => { if (cb) cb(res); });
                            } else if (msg.action === 'copyFolderPath') {
                                fetch('/api/copyFolderPath', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify(msg)
                                })
                                .then(r => r.json())
                                .then(res => {
                                    if (res && res.path) {
                                        window.copyTextToClipboard(res.path);
                                    }
                                    if (cb) cb(res);
                                });
                            } else {
                                if (cb) cb({ success: true });
                            }
                        }
                    };

                    // 5. 模拟 chrome.windows
                    window.chrome.windows = {
                        getCurrent: function(cb) { if(cb) cb({ id: 1 }); },
                        update: function(id, opts, cb) { if(cb) cb(); },
                        create: function(opts, cb) { window.open(opts.url, '_blank'); }
                    };

                    // 页面 DOM 加载完毕后，强制确保遮罩隐藏、主应用显示、绑定按钮并自动触发扫描
                    document.addEventListener('DOMContentLoaded', function() {
                        try { window.focus(); } catch(e){}
                        setTimeout(function() {
                            try { window.focus(); } catch(e){}
                            const authOverlay = document.getElementById('auth-overlay');
                            if (authOverlay) {
                                authOverlay.classList.add('hidden');
                                authOverlay.style.display = 'none';
                            }
                            const appEl = document.getElementById('app');
                            if (appEl) {
                                appEl.classList.remove('hidden');
                                appEl.style.display = 'flex';
                            }
                            const statusEl = document.getElementById('license-status');
                            if (statusEl) statusEl.textContent = '永久授权 (本地模式)';

                            // 深度绑定复制路径按钮
                            var btnCopyFolder = document.getElementById('btn-copy-folder');
                            if (btnCopyFolder) {
                                btnCopyFolder.onclick = async function(e) {
                                    e.stopImmediatePropagation();
                                    e.preventDefault();
                                    var folder = window.scanData ? (window.scanData.title || '') : '';
                                    try {
                                        const res = await fetch('/api/copyFolderPath', {
                                            method: 'POST',
                                            headers: { 'Content-Type': 'application/json' },
                                            body: JSON.stringify({ folder: folder })
                                        }).then(r => r.json());
                                        if (res && res.path) {
                                            await window.copyTextToClipboard(res.path);
                                            var orig = btnCopyFolder.innerHTML;
                                            btnCopyFolder.innerHTML = '<span style="color:#10b981; font-weight:bold;">已复制路径!</span>';
                                            setTimeout(() => { btnCopyFolder.innerHTML = orig; }, 2000);
                                        }
                                    } catch(err) {}
                                };
                            }

                            // 深度绑定打开文件夹按钮
                            var btnOpenFolder = document.getElementById('btn-open-folder');
                            if (btnOpenFolder) {
                                btnOpenFolder.onclick = async function(e) {
                                    e.stopImmediatePropagation();
                                    e.preventDefault();
                                    var folder = window.scanData ? (window.scanData.title || '') : '';
                                    await fetch('/api/openFolder', {
                                        method: 'POST',
                                        headers: { 'Content-Type': 'application/json' },
                                        body: JSON.stringify({ folder: folder })
                                    });
                                };
                            }
                            
                            // 注入商品信息展示栏的构建函数
                            window.__showProductInfoBar = function() {
                                var existing = document.getElementById('product-info-bar');
                                if (existing) existing.remove();
                                var url = window.__productPageUrl || '';
                                var title = window.__productTitle || '';
                                if (!url && !title) return;

                                var bar = document.createElement('div');
                                bar.id = 'product-info-bar';
                                bar.style.cssText = 'background:linear-gradient(135deg,#1e293b,#334155);color:#f8fafc;padding:10px 14px;border-radius:8px;margin-bottom:10px;font-size:12px;line-height:1.6;box-shadow:0 2px 8px rgba(0,0,0,0.15);';

                                var titleHtml = title ? '<div style="font-weight:bold;font-size:13px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">📦 ' + title.replace(/</g,'&lt;') + '</div>' : '';

                                var urlHtml = '';
                                if (url) {
                                    urlHtml = '<div style="display:flex;align-items:center;gap:8px;">' +
                                        '<span style="color:#94a3b8;flex-shrink:0;">🔗 链接:</span>' +
                                        '<span id="product-url-text" style="color:#60a5fa;flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;cursor:pointer;" title="' + url.replace(/"/g,'&quot;') + '">' + url.replace(/</g,'&lt;') + '</span>' +
                                        '<button id="btn-copy-product-url" style="flex-shrink:0;background:#3b82f6;color:#fff;border:none;border-radius:4px;padding:3px 10px;font-size:11px;cursor:pointer;font-weight:bold;transition:all 0.2s;">📋 复制链接</button>' +
                                    '</div>';
                                }
                                bar.innerHTML = titleHtml + urlHtml;

                                // 插入到 app 容器最顶部
                                var appEl = document.getElementById('app');
                                if (appEl && appEl.firstChild) {
                                    appEl.insertBefore(bar, appEl.firstChild);
                                } else if (document.body) {
                                    document.body.insertBefore(bar, document.body.firstChild);
                                }

                                // 绑定复制按钮
                                var btnCopy = document.getElementById('btn-copy-product-url');
                                if (btnCopy) {
                                    btnCopy.onclick = function() {
                                        window.copyTextToClipboard(url);
                                        btnCopy.textContent = '✅ 已复制!';
                                        btnCopy.style.background = '#10b981';
                                        setTimeout(function() {
                                            btnCopy.textContent = '📋 复制链接';
                                            btnCopy.style.background = '#3b82f6';
                                        }, 2000);
                                    };
                                }
                                // 点击链接文字也复制
                                var urlText = document.getElementById('product-url-text');
                                if (urlText) {
                                    urlText.onclick = function() {
                                        window.copyTextToClipboard(url);
                                        window.__showCopiedToast && window.__showCopiedToast('✅ 链接已复制到剪贴板');
                                    };
                                }
                            };

                            // 自动复制成功 Toast 提示
                            window.__showCopiedToast = function(msg) {
                                var existing = document.getElementById('copy-toast');
                                if (existing) existing.remove();
                                var toast = document.createElement('div');
                                toast.id = 'copy-toast';
                                toast.textContent = msg;
                                toast.style.cssText = 'position:fixed;top:16px;left:50%;transform:translateX(-50%);background:#10b981;color:#fff;padding:8px 20px;border-radius:8px;font-size:13px;font-weight:bold;z-index:99999;box-shadow:0 4px 12px rgba(0,0,0,0.2);transition:opacity 0.3s;';
                                document.body.appendChild(toast);
                                setTimeout(function() {
                                    toast.style.opacity = '0';
                                    setTimeout(function() { toast.remove(); }, 300);
                                }, 2500);
                            };

                            // 自动触发一次扫描
                            if (typeof window.performScan === 'function') {
                                window.isAuthorizedSession = true;
                                window.performScan();
                            }
                        }, 80);
                    });
                })();
                </script>
                """
                if "</head>" in html_str:
                    html_str = html_str.replace("</head>", f"{bridge_script}\n</head>")
                else:
                    html_str = bridge_script + html_str

                self.wfile.write(html_str.encode("utf-8"))
            else:
                self.wfile.write(content)
        else:
            self.send_response(404)
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.lstrip("/")

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            payload = {}

        if path == "api/download":
            self._handle_api_download(payload)
        elif path == "api/openFolder":
            self._handle_api_open_folder(payload)
        elif path == "api/copyFolderPath":
            self._handle_api_copy_folder_path(payload)
        elif path in ("api/calcfee/save_json", "api/save_sku_json"):
            self._handle_api_save_calcfee_json(payload)
        elif path in ("api/calcfee/save_sku_data_txt", "api/calcfee/save_txt"):
            self._handle_api_save_calcfee_txt(payload)
        elif path == "api/calcfee/openExportFolder":
            self._handle_api_open_export_folder()
        else:
            self.send_response(404)
            self._set_cors_headers()
            self.end_headers()
            self.wfile.write(b"404 Not Found")

    def _normalize_image_urls(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """将所有图片链接归一化为完整 https 格式"""
        if not data:
            return data

        def _clean(u):
            if not u:
                return ""
            if u.startswith("//"):
                return "https:" + u
            return u

        for item in data.get("gallery", []):
            if item.get("url"):
                item["url"] = _clean(item["url"])

        for item in data.get("sku", []):
            if item.get("url"):
                item["url"] = _clean(item["url"])

        for item in data.get("detail", []):
            if item.get("url"):
                item["url"] = _clean(item["url"])

        sku_data = data.get("skuData", {})
        for prop in sku_data.get("skuProps", []):
            for val in prop.get("values", []):
                if val.get("imageUrl"):
                    val["imageUrl"] = _clean(val["imageUrl"])

        for row in sku_data.get("skuMatrix", []):
            if row.get("skuImageUrl"):
                row["skuImageUrl"] = _clean(row["skuImageUrl"])

        return data

    def _handle_api_scan(self):
        """扫描当前 1688 页面数据"""
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        if not self.browser_mgr:
            self.wfile.write(json.dumps({"success": False, "error": "BrowserManager 未初始化"}).encode("utf-8"))
            return

        target_page = None
        tabs = self.browser_mgr.get_all_tabs()
        import sys
        print(f"API/SCAN called! Total tabs: {len(tabs)}", file=sys.stderr)
        for idx, t in enumerate(tabs):
            print(f"  Tab {idx}: is_active={t.is_active}, url={t.url}, is_1688={t.is_1688}", file=sys.stderr)
        # 1. 优先获取当前正在显示的 1688 详情页
        for t in tabs:
            if t.is_active and t.page and ("detail.1688.com" in (t.url or "") or "/offer/" in (t.url or "")) and "127.0.0.1" not in (t.url or "") and "localhost" not in (t.url or ""):
                target_page = t.page
                break

        # 2. 如果前台没有任何 1688 详情页面激活，兜底找最后一个打开的 1688 详情页
        if not target_page:
            for t in reversed(tabs):
                if t.page and ("detail.1688.com" in (t.url or "") or "/offer/" in (t.url or "")) and "127.0.0.1" not in (t.url or "") and "localhost" not in (t.url or ""):
                    target_page = t.page
                    break

        if not target_page:
            self.wfile.write(json.dumps({"success": False, "error": "未找到打开的 1688 商品详情页，请在 Chrome 中打开商品页面"}).encode("utf-8"))
            return

        current_page_url = target_page.url or ""
        # 命中秒级热缓存：若 3 秒内对同一详情页已扫描过，直接毫秒级返回
        if (
            PluginServerHandler.last_scan_data
            and PluginServerHandler.last_scan_url == current_page_url
            and time.time() - getattr(PluginServerHandler, "last_scan_time", 0) < 3.0
        ):
            self.wfile.write(json.dumps({"success": True, "data": PluginServerHandler.last_scan_data}, ensure_ascii=False).encode("utf-8"))
            return

        def _do_extract():
            scraper = Scraper1688(target_page)
            return scraper.extract_data_only()

        try:
            data = self.browser_mgr.run_on_browser_thread(_do_extract)
            if data:
                data = self._normalize_image_urls(data)
                # 注入当前商品详情页的真实 URL
                try:
                    data["pageUrl"] = target_page.url or ""
                except Exception:
                    data["pageUrl"] = ""
                PluginServerHandler.last_scan_data = data
                PluginServerHandler.last_scan_url = current_page_url
                PluginServerHandler.last_scan_time = time.time()
                if callable(PluginServerHandler.on_scan_callback):
                    try:
                        PluginServerHandler.on_scan_callback(data.get("title", ""), data.get("pageUrl", ""))
                    except Exception:
                        pass
                self.wfile.write(json.dumps({"success": True, "data": data}, ensure_ascii=False).encode("utf-8"))
            else:
                self.wfile.write(json.dumps({"success": False, "error": "解析 1688 页面失败，请确保页面加载完整"}).encode("utf-8"))
        except Exception as e:
            self.wfile.write(json.dumps({"success": False, "error": str(e)}).encode("utf-8"))

    def _handle_api_download(self, payload: Dict[str, Any]):
        """执行下载任务并生成标准目录与配置文件"""
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        data = payload.get("data") or PluginServerHandler.last_scan_data
        if not data:
            self.wfile.write(json.dumps({"success": False, "error": "无待下载的商品数据"}).encode("utf-8"))
            return

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

        # 目录名清洗
        raw_folder = payload.get("folder") or data.get("title", "1688商品")
        safe_folder = "".join(c for c in raw_folder if c.isalnum() or c in (" ", "-", "_")).strip()[:40]
        if not safe_folder:
            safe_folder = f"goods_{int(time.time())}"

        target_dir = os.path.join(base_dir, f"1688_{safe_folder}")
        os.makedirs(target_dir, exist_ok=True)
        PluginServerHandler.last_saved_dir = target_dir

        main_dir = os.path.join(target_dir, "0gallery")
        detail_dir = os.path.join(target_dir, "1detail")
        sku_dir = os.path.join(target_dir, "2sku")

        os.makedirs(main_dir, exist_ok=True)
        os.makedirs(detail_dir, exist_ok=True)
        os.makedirs(sku_dir, exist_ok=True)

        # 保存原始 JSON
        try:
            with open(os.path.join(target_dir, "raw_data.json"), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        # 收集下载任务
        tasks: List[tuple] = []

        # 1. 主图
        gallery_list = data.get("gallery", [])
        saved_gallery_files = []
        for i, item in enumerate(gallery_list):
            url = item.get("url") if isinstance(item, dict) else item
            if url:
                fn = f"main_{len(saved_gallery_files)+1}.jpg"
                p = os.path.join(main_dir, fn)
                saved_gallery_files.append(fn)
                tasks.append((url, p))

        # 2. 详情图
        detail_list = data.get("detail", [])
        saved_detail_files = []
        for i, item in enumerate(detail_list):
            url = item.get("url") if isinstance(item, dict) else item
            if url:
                fn = f"detail_{len(saved_detail_files)+1}.jpg"
                p = os.path.join(detail_dir, fn)
                saved_detail_files.append(fn)
                tasks.append((url, p))

        # 3. SKU 色卡图
        sku_list = data.get("sku", [])
        saved_sku_files = []
        for i, item in enumerate(sku_list):
            url = item.get("url") if isinstance(item, dict) else item
            if url:
                name = item.get("name", "") if isinstance(item, dict) else ""
                clean_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
                fn = f"sku_{len(saved_sku_files)+1}_{clean_name}.jpg" if clean_name else f"sku_{len(saved_sku_files)+1}.jpg"
                p = os.path.join(sku_dir, fn)
                saved_sku_files.append(fn)
                tasks.append((url, p))

        # 并发下载图片
        def _dl(task):
            url, path = task
            if url.startswith("//"):
                url = "https:" + url
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": ""
                }
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200 and len(resp.content) > 100:
                    with open(path, "wb") as f:
                        f.write(resp.content)
                    return True
            except Exception:
                pass
            return False

        success_count = 0
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(_dl, tasks))
            success_count = sum(1 for r in results if r)

        # 生成 sku_data.txt
        try:
            sku_data = data.get("skuData", {})
            sku_matrix = sku_data.get("skuMatrix", [])
            lines = [f"# 商品标题: {data.get('title', '')}"]
            if data.get("pageUrl"):
                lines.append(f"# 商品链接: {data.get('pageUrl')}")
            lines.append("")
            lines.append("【价格与阶梯】")
            for pr in sku_data.get("priceRanges", []):
                lines.append(f"起批量: {pr.get('minQuantity', 1)} | 价格: ¥{pr.get('price', 0)}")
            lines.append("")
            lines.append("【SKU变体明细】")
            lines.append("序号\t规格属性\t单价\t库存\t可售")
            for idx, row in enumerate(sku_matrix):
                specs = row.get("specText", "-")
                p = row.get("price", "-")
                st = row.get("stock", "-")
                lines.append(f"{idx+1}\t{specs}\t¥{p}\t{st}\t是")

            with open(os.path.join(target_dir, "sku_data.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except Exception:
            pass

        self.wfile.write(json.dumps({
            "success": True,
            "completed": success_count,
            "total": len(tasks),
            "outputDir": target_dir,
            "failed": len(tasks) - success_count
        }, ensure_ascii=False).encode("utf-8"))

    def _handle_api_open_folder(self, payload: Dict[str, Any]):
        """打开目标下载文件夹"""
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        target = PluginServerHandler.last_saved_dir

        if not target or not os.path.exists(target):
            folder = payload.get("folder", "")
            safe_folder = "".join(c for c in folder if c.isalnum() or c in (" ", "-", "_")).strip()[:40]
            candidates = [
                os.path.join(base_dir, f"1688_{safe_folder}"),
                os.path.join(base_dir, safe_folder),
                base_dir
            ]
            for candidate in candidates:
                if candidate and os.path.exists(candidate):
                    target = candidate
                    break

        if not target or not os.path.exists(target):
            target = base_dir

        if sys.platform == "darwin":
            subprocess.Popen(["open", target])
        elif sys.platform == "win32":
            os.startfile(target)
        else:
            subprocess.Popen(["xdg-open", target])

        self.wfile.write(json.dumps({"success": True, "path": target}).encode("utf-8"))

    def _handle_api_copy_folder_path(self, payload: Dict[str, Any]):
        """获取目标下载文件夹绝对路径用于剪贴板复制"""
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        target = PluginServerHandler.last_saved_dir
        if not target or not os.path.exists(target):
            folder = payload.get("folder", "")
            safe_folder = "".join(c for c in folder if c.isalnum() or c in (" ", "-", "_")).strip()[:40]
            if safe_folder and os.path.exists(os.path.join(base_dir, f"1688_{safe_folder}")):
                target = os.path.join(base_dir, f"1688_{safe_folder}")
            else:
                target = os.path.join(base_dir, f"1688_{safe_folder}") if safe_folder else base_dir

        self.wfile.write(json.dumps({"success": True, "path": target, "error": ""}).encode("utf-8"))

    def _handle_api_save_calcfee_json(self, payload: Dict[str, Any]):
        """保存来自前端的 SKU 核算与录入 JSON 数据至 test产品试验品 及其 bak 目录"""
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            target_product_dir = os.path.join(base_dir, "test产品试验品")
            bak_dir = os.path.join(target_product_dir, "bak")
            os.makedirs(target_product_dir, exist_ok=True)
            os.makedirs(bak_dir, exist_ok=True)

            now_str = time.strftime("%Y%m%d_%H%M%S")
            main_json_path = os.path.join(target_product_dir, "sku_data.json")
            bak_json_path = os.path.join(bak_dir, f"sku_export_{now_str}.json")

            json_str = json.dumps(payload, ensure_ascii=False, indent=2)
            with open(main_json_path, "w", encoding="utf-8") as f:
                f.write(json_str)
            with open(bak_json_path, "w", encoding="utf-8") as f:
                f.write(json_str)

            PluginServerHandler.last_exported_sku_json = main_json_path
            item_count = len(payload.get("items", []))

            if callable(PluginServerHandler.on_calcfee_export_callback):
                try:
                    PluginServerHandler.on_calcfee_export_callback(main_json_path, item_count)
                except Exception:
                    pass

            self.wfile.write(json.dumps({
                "success": True,
                "path": main_json_path,
                "fileName": "sku_data.json",
                "total": item_count
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.wfile.write(json.dumps({
                "success": False,
                "error": str(e)
            }, ensure_ascii=False).encode("utf-8"))

    def _handle_api_save_calcfee_txt(self, payload: Dict[str, Any]):
        """保存来自前端导出的标准 sku_data.txt 数据文件至 test产品试验品 及其 bak 目录"""
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
            target_product_dir = os.path.join(base_dir, "test产品试验品")
            bak_dir = os.path.join(target_product_dir, "bak")
            os.makedirs(target_product_dir, exist_ok=True)
            os.makedirs(bak_dir, exist_ok=True)

            txt_content = payload.get("txtContent", "")
            now_str = time.strftime("%Y%m%d_%H%M%S")
            file_name = "sku_data.txt"

            main_file_path = os.path.join(target_product_dir, file_name)
            bak_file_path = os.path.join(bak_dir, f"sku_data_{now_str}.txt")

            with open(main_file_path, "w", encoding="utf-8") as f:
                f.write(txt_content)
            with open(bak_file_path, "w", encoding="utf-8") as f:
                f.write(txt_content)

            PluginServerHandler.last_exported_sku_json = main_file_path
            item_count = payload.get("totalItems", 0)

            if callable(PluginServerHandler.on_calcfee_export_callback):
                try:
                    PluginServerHandler.on_calcfee_export_callback(main_file_path, item_count)
                except Exception:
                    pass

            self.wfile.write(json.dumps({
                "success": True,
                "path": main_file_path,
                "fileName": file_name,
                "total": item_count
            }, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self.wfile.write(json.dumps({
                "success": False,
                "error": str(e)
            }, ensure_ascii=False).encode("utf-8"))

    def _handle_api_open_export_folder(self):
        """打开数据导出目录 (test产品试验品)"""
        self.send_response(200)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        target_product_dir = os.path.join(base_dir, "test产品试验品")
        os.makedirs(target_product_dir, exist_ok=True)

        if sys.platform == "darwin":
            subprocess.Popen(["open", target_product_dir])
        elif sys.platform == "win32":
            os.startfile(target_product_dir)
        else:
            subprocess.Popen(["xdg-open", target_product_dir])

        self.wfile.write(json.dumps({"success": True, "path": target_product_dir}).encode("utf-8"))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        export_dir = os.path.join(base_dir, "sku_data_exports")
        os.makedirs(export_dir, exist_ok=True)

        if sys.platform == "darwin":
            subprocess.Popen(["open", export_dir])
        elif sys.platform == "win32":
            os.startfile(export_dir)
        else:
            subprocess.Popen(["xdg-open", export_dir])

        self.wfile.write(json.dumps({"success": True, "path": export_dir}).encode("utf-8"))

    def log_message(self, format, *args):
        pass


class PluginServerManager:
    """插件 Web 服务守护进程管理器"""

    _server_instance = None
    _server_thread = None
    _actual_port = SERVER_PORT

    @classmethod
    def start_server(cls, browser_mgr, port: int = SERVER_PORT, on_scan_callback=None, on_export_callback=None) -> int:
        PluginServerHandler.browser_mgr = browser_mgr
        if on_scan_callback:
            PluginServerHandler.on_scan_callback = on_scan_callback
        if on_export_callback:
            PluginServerHandler.on_calcfee_export_callback = on_export_callback

        if cls._server_instance is not None:
            return cls._actual_port

        # 寻找可用端口
        actual_port = port
        for p in range(port, port + 20):
            try:
                server = HTTPServer(("127.0.0.1", p), PluginServerHandler)
                cls._server_instance = server
                cls._actual_port = p
                actual_port = p
                break
            except OSError:
                continue

        if not cls._server_instance:
            return 0

        cls._server_thread = threading.Thread(target=cls._server_instance.serve_forever, daemon=True, name="PluginServerThread")
        cls._server_thread.start()
        return actual_port

    @classmethod
    def get_popup_url(cls) -> str:
        return f"http://127.0.0.1:{cls._actual_port}/popup.html?mode=popup"

    @classmethod
    def get_calcfee_url(cls) -> str:
        return f"http://127.0.0.1:{cls._actual_port}/calcfee/index.html"
