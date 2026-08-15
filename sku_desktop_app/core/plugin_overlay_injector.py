"""
1688 Chrome 插件浮层与弹窗注入模块
将 1688-Image-Downloader 的完整 UI (popup.html + popup.css) 作为 Chrome 页面内浮层/弹窗直接唤起并自动扫描
"""
import os
import sys
import json
import time
import subprocess
from typing import Optional, Callable
from playwright.sync_api import Page

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.scraper_1688 import Scraper1688

PLUGIN_DIR = "/Users/gx/Desktop/mypro/1688-Image-Downloader"


def inject_plugin_ui_into_1688_page(page: Page, default_output_dir: str = "", log_fn: Optional[Callable[[str, str], None]] = None) -> bool:
    """
    在当前 1688 商品页面直接注入并弹出 1688-Image-Downloader 插件的完整暗色科技感 UI 面板
    """
    if not os.path.exists(PLUGIN_DIR):
        return False

    if not default_output_dir:
        default_output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    popup_html_path = os.path.join(PLUGIN_DIR, "popup.html")
    popup_css_path = os.path.join(PLUGIN_DIR, "popup.css")
    collector_js_path = os.path.join(PLUGIN_DIR, "1688_sku_collector.js")
    content_js_path = os.path.join(PLUGIN_DIR, "content.js")

    with open(popup_html_path, "r", encoding="utf-8") as f:
        raw_html = f.read()
    with open(popup_css_path, "r", encoding="utf-8") as f:
        raw_css = f.read()
    with open(collector_js_path, "r", encoding="utf-8") as f:
        collector_js = f.read()
    with open(content_js_path, "r", encoding="utf-8") as f:
        content_js = f.read()

    # 提取 popup.html 内部的 body 部分
    body_content = raw_html
    if "<body" in raw_html:
        start_idx = raw_html.find("<body")
        start_body = raw_html.find(">", start_idx) + 1
        end_body = raw_html.rfind("</body>")
        if start_body > 0 and end_body > start_body:
            body_content = raw_html[start_body:end_body]

    body_content = body_content.replace('<script src="popup.js"></script>', '')

    # 绑定 Python 下载处理桥接函数到页面全局
    try:
        def _py_download_bridge(source, payload_json_str):
            try:
                payload = json.loads(payload_json_str)
                raw_data = payload.get("data", {})
                selection = payload.get("selection", {})
                base_dir = payload.get("outputDir", default_output_dir)

                scraper = Scraper1688(page, log_fn=log_fn)
                ok, out_dir, stats = scraper.download_selected_assets(
                    raw_data, selection, base_dir
                )
                return json.dumps({"success": ok, "outputDir": out_dir, "stats": stats, "error": str(out_dir) if not ok else ""})
            except Exception as e:
                return json.dumps({"success": False, "error": str(e)})

        def _py_open_folder_bridge(source, target_dir):
            if target_dir and os.path.exists(target_dir):
                if sys.platform == "darwin":
                    subprocess.Popen(["open", target_dir])
                elif sys.platform == "win32":
                    os.startfile(target_dir)
                else:
                    subprocess.Popen(["xdg-open", target_dir])
                return True
            return False

        # 如果未注入过函数则注入
        try:
            page.expose_binding("__ag_py_download_assets", _py_download_bridge)
        except Exception:
            pass

        try:
            page.expose_binding("__ag_py_open_folder", _py_open_folder_bridge)
        except Exception:
            pass

    except Exception:
        pass

    # 注入脚本
    injection_script = f"""
    (() => {{
        // 1. 如果已存在旧弹窗，先置顶并重新扫描
        let existing = document.getElementById('ag-1688-plugin-modal-wrapper');
        if (existing) {{
            existing.style.display = 'flex';
            existing.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            const scanBtn = existing.querySelector('#btn-scan');
            if (scanBtn) scanBtn.click();
            return true;
        }}

        // 2. 注入全局 chrome.runtime 模拟对象
        if (typeof window.chrome === 'undefined') window.chrome = {{}};
        if (typeof window.chrome.runtime === 'undefined') {{
            window.chrome.runtime = {{
                onMessage: {{ addListener: function() {{}} }},
                sendMessage: function(msg, cb) {{
                    if (cb) cb({{ success: true }});
                }},
                getURL: function(path) {{ return path; }}
            }};
        }}

        // 3. 注入 SkuCollector1688（解除 AMD define 拦截）
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

        // 4. 创建外层容器浮层 (可拖拽 / 可关闭 / 居中弹出)
        const wrapper = document.createElement('div');
        wrapper.id = 'ag-1688-plugin-modal-wrapper';
        wrapper.style.cssText = `
            position: fixed;
            top: 24px;
            right: 24px;
            width: 860px;
            max-width: 92vw;
            height: calc(100vh - 48px);
            max-height: 94vh;
            background: #0f172a;
            color: #e2e8f0;
            z-index: 2147483647;
            box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.9), 0 0 0 1px rgba(244, 63, 94, 0.35);
            border-radius: 16px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            animation: agFadeSlideIn 0.28s cubic-bezier(0.16, 1, 0.3, 1);
        `;

        // 5. 注入 CSS
        let styleEl = document.getElementById('ag-1688-plugin-style');
        if (!styleEl) {{
            styleEl = document.createElement('style');
            styleEl.id = 'ag-1688-plugin-style';
            styleEl.textContent = `
                @keyframes agFadeSlideIn {{
                    from {{ opacity: 0; transform: translateY(-16px) scale(0.98); }}
                    to {{ opacity: 1; transform: translateY(0) scale(1); }}
                }}
                #ag-1688-plugin-modal-wrapper * {{
                    box-sizing: border-box;
                }}
                #ag-1688-plugin-modal-wrapper #container {{
                    width: 100% !important;
                    height: 100% !important;
                    max-width: none !important;
                    min-height: 0 !important;
                    display: flex !important;
                    flex-direction: column !important;
                    background: transparent !important;
                    border-radius: 0 !important;
                    box-shadow: none !important;
                    padding: 0 !important;
                }}
                #ag-1688-plugin-modal-wrapper #header {{
                    display: none !important;
                }}
                #ag-1688-plugin-modal-wrapper #result-container {{
                    flex: 1 !important;
                    overflow-y: auto !important;
                    padding: 12px 16px !important;
                }}
                #ag-1688-plugin-modal-wrapper .close-floating-btn {{
                    background: #ef4444;
                    color: #ffffff;
                    border: none;
                    border-radius: 6px;
                    padding: 4px 12px;
                    font-weight: 600;
                    font-size: 13px;
                    cursor: pointer;
                    transition: all 0.15s ease;
                }}
                #ag-1688-plugin-modal-wrapper .close-floating-btn:hover {{
                    background: #dc2626;
                    transform: scale(1.04);
                }}
                #ag-1688-plugin-modal-wrapper .thumb-card {{
                    position: relative;
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 6px;
                    display: inline-flex;
                    flex-direction: column;
                    align-items: center;
                    width: 130px;
                    margin: 6px;
                    transition: all 0.2s;
                }}
                #ag-1688-plugin-modal-wrapper .thumb-card:hover {{
                    border-color: #ec4899;
                    box-shadow: 0 4px 12px rgba(236, 72, 153, 0.25);
                }}
                #ag-1688-plugin-modal-wrapper .thumb-checkbox {{
                    position: absolute;
                    top: 8px;
                    left: 8px;
                    width: 18px;
                    height: 18px;
                    cursor: pointer;
                    z-index: 2;
                    accent-color: #ec4899;
                }}
                #ag-1688-plugin-modal-wrapper .thumb-img {{
                    width: 100%;
                    height: 110px;
                    object-fit: cover;
                    border-radius: 4px;
                    cursor: zoom-in;
                    background: #020617;
                }}
                #ag-1688-plugin-modal-wrapper .thumb-name {{
                    margin-top: 4px;
                    font-size: 11px;
                    color: #cbd5e1;
                    max-width: 100%;
                    overflow: hidden;
                    text-overflow: ellipsis;
                    white-space: nowrap;
                    text-align: center;
                }}
                {raw_css}
            `;
            document.head.appendChild(styleEl);
        }}

        // 6. 填充 HTML 结构
        wrapper.innerHTML = `
            <div id="ag-plugin-drag-bar" style="display:flex; align-items:center; justify-content:space-between; background:#1e293b; padding:10px 18px; border-bottom:1px solid #334155; cursor:move; user-select:none;">
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:16px;">🛍️</span>
                    <strong style="color:#fbcfe8; font-size:14px; letter-spacing:0.5px;">1688 素材采集与预览工作台 (插件版)</strong>
                    <span style="font-size:11px; background:#065f46; color:#a7f3d0; padding:2px 6px; border-radius:4px; margin-left:4px;">Ready</span>
                </div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <button type="button" class="close-floating-btn" id="btn-close-plugin-modal" title="关闭 (Esc)">✕ 关闭</button>
                </div>
            </div>
            <div style="flex:1; overflow-y:auto; position:relative; background:#0f172a; display:flex; flex-direction:column;" id="plugin-modal-body-container">
                {body_content}
            </div>
        `;

        document.body.appendChild(wrapper);

        // 7. 关闭与键盘 Esc 事件
        const closeBtn = wrapper.querySelector('#btn-close-plugin-modal');
        const closeModal = () => {{
            wrapper.remove();
        }};
        if (closeBtn) closeBtn.onclick = closeModal;

        window.addEventListener('keydown', (e) => {{
            if (e.key === 'Escape') {{
                const modal = document.getElementById('ag-1688-plugin-modal-wrapper');
                if (modal) modal.remove();
            }}
        }}, {{ once: true }});

        // 8. 标题栏拖拽移动
        const dragBar = wrapper.querySelector('#ag-plugin-drag-bar');
        let isDragging = false;
        let startX, startY, initialLeft, initialTop;

        dragBar.onmousedown = (e) => {{
            if (e.target === closeBtn) return;
            isDragging = true;
            startX = e.clientX;
            startY = e.clientY;
            const rect = wrapper.getBoundingClientRect();
            initialLeft = rect.left;
            initialTop = rect.top;
            wrapper.style.right = 'auto';
            wrapper.style.left = initialLeft + 'px';
            wrapper.style.top = initialTop + 'px';

            const onMouseMove = (ev) => {{
                if (!isDragging) return;
                const dx = ev.clientX - startX;
                const dy = ev.clientY - startY;
                wrapper.style.left = Math.max(10, Math.min(window.innerWidth - wrapper.offsetWidth - 10, initialLeft + dx)) + 'px';
                wrapper.style.top = Math.max(10, Math.min(window.innerHeight - wrapper.offsetHeight - 10, initialTop + dy)) + 'px';
            }};

            const onMouseUp = () => {{
                isDragging = false;
                document.removeEventListener('mousemove', onMouseMove);
                document.removeEventListener('mouseup', onMouseUp);
            }};

            document.addEventListener('mousemove', onMouseMove);
            document.addEventListener('mouseup', onMouseUp);
        }};

        // 9. 提取与渲染核心逻辑
        let currentData = null;
        let savedDownloadDir = '';

        const runExtraction = () => {{
            try {{
                const data = {content_js};
                if (data && !data.title) {{
                    const el = document.querySelector('h1, .title-text, .od-title, [class*="product-title"]');
                    if (el) data.title = el.innerText.trim();
                    else data.title = (document.title || '').split('-')[0].replace('【阿里巴巴】', '').trim();
                }}
                return data;
            }} catch(e) {{
                return null;
            }}
        }};

        // 获取 DOM 元素
        const scanBtn = wrapper.querySelector('#btn-scan');
        const btnDownload = wrapper.querySelector('#btn-download');
        const btnOpenFolder = wrapper.querySelector('#btn-open-folder');
        const actionsSecondary = wrapper.querySelector('#actions-secondary');
        const resultsArea = wrapper.querySelector('#results-area');
        const statusArea = wrapper.querySelector('#status-area');
        const statusText = wrapper.querySelector('#status-text');
        const progressArea = wrapper.querySelector('#progress-area');
        const progressBarFill = wrapper.querySelector('#progress-bar-fill');
        const progressText = wrapper.querySelector('#progress-text');

        const badgeTitle = wrapper.querySelector('#badge-title');
        const badgeGallery = wrapper.querySelector('#badge-gallery');
        const badgeSku = wrapper.querySelector('#badge-sku');
        const badgeDetail = wrapper.querySelector('#badge-detail');

        const galleryThumbs = wrapper.querySelector('#gallery-thumbs');
        const skuThumbs = wrapper.querySelector('#sku-thumbs');
        const detailThumbs = wrapper.querySelector('#detail-thumbs');
        const skuDataPanel = wrapper.querySelector('#sku-data-panel');
        const skuListContent = wrapper.querySelector('#sku-tab-content-list');
        const skuTableContent = wrapper.querySelector('#sku-tab-content-table');
        const skuJsonCode = wrapper.querySelector('#sku-json-code');

        // Lightbox 查看大图
        const showLightbox = (url, title) => {{
            let lb = document.getElementById('ag-lightbox-fullscreen');
            if (lb) lb.remove();

            lb = document.createElement('div');
            lb.id = 'ag-lightbox-fullscreen';
            lb.style.cssText = `
                position:fixed; top:0; left:0; width:100vw; height:100vh;
                background:rgba(15,23,42,0.92); backdrop-filter:blur(8px);
                z-index:2147483648; display:flex; flex-direction:column;
                align-items:center; justify-content:center; padding:20px;
                animation:agFadeSlideIn 0.2s ease;
            `;
            lb.innerHTML = `
                <button type="button" style="position:absolute; top:20px; right:25px; width:38px; height:38px; border-radius:50%; background:#ef4444; color:#fff; border:none; font-size:22px; cursor:pointer; font-weight:bold; box-shadow:0 4px 12px rgba(0,0,0,0.5);">✕</button>
                <img src="${{url}}" style="max-width:90vw; max-height:85vh; object-fit:contain; border-radius:8px; box-shadow:0 20px 50px rgba(0,0,0,0.8); background:#000;">
                <div style="margin-top:12px; color:#e2e8f0; font-size:14px; font-weight:600; text-align:center;">${{title || ''}}</div>
            `;
            lb.querySelector('button').onclick = () => lb.remove();
            lb.onclick = (e) => {{ if (e.target === lb) lb.remove(); }};
            document.body.appendChild(lb);
        }};

        const renderResults = (data) => {{
            if (!data) return;
            currentData = data;
            if (statusArea) statusArea.classList.add('hidden');
            if (resultsArea) resultsArea.classList.remove('hidden');
            if (btnDownload) {{
                btnDownload.classList.remove('hidden');
                btnDownload.disabled = false;
            }}

            if (badgeTitle) {{
                badgeTitle.textContent = (data.title || '').length > 30 ? (data.title.substring(0, 28) + '...') : data.title;
                badgeTitle.title = data.title;
            }}
            if (badgeGallery) badgeGallery.textContent = data.gallery.length;
            if (badgeSku) badgeSku.textContent = data.sku.length;
            if (badgeDetail) badgeDetail.textContent = data.detail.length;

            // 1. 渲染主图
            if (galleryThumbs) {{
                galleryThumbs.innerHTML = '';
                galleryThumbs.classList.remove('hidden');
                data.gallery.forEach((img, idx) => {{
                    const card = document.createElement('div');
                    card.className = 'thumb-card';
                    card.innerHTML = `
                        <input type="checkbox" checked class="thumb-checkbox" data-type="gallery" data-idx="${{idx}}">
                        <img src="${{img.url}}" class="thumb-img" loading="lazy">
                        <span class="thumb-name">${{img.name}}</span>
                    `;
                    card.querySelector('img').onclick = () => showLightbox(img.url, img.name);
                    galleryThumbs.appendChild(card);
                }});
            }}

            // 2. 渲染 SKU 色卡
            if (skuListContent) {{
                skuListContent.innerHTML = '';
                data.sku.forEach((img, idx) => {{
                    const card = document.createElement('div');
                    card.className = 'thumb-card';
                    const cleanName = img.name.replace(/^sku_\\d+_/, '');
                    card.innerHTML = `
                        <input type="checkbox" checked class="thumb-checkbox" data-type="sku" data-idx="${{idx}}">
                        <img src="${{img.url}}" class="thumb-img" loading="lazy">
                        <span class="thumb-name" title="${{cleanName}}">${{cleanName}}</span>
                    `;
                    card.querySelector('img').onclick = () => showLightbox(img.url, cleanName);
                    skuListContent.appendChild(card);
                }});
            }}

            // 3. 渲染详情图
            if (detailThumbs) {{
                detailThumbs.innerHTML = '';
                data.detail.forEach((img, idx) => {{
                    const card = document.createElement('div');
                    card.className = 'thumb-card';
                    card.innerHTML = `
                        <input type="checkbox" checked class="thumb-checkbox" data-type="detail" data-idx="${{idx}}">
                        <img src="${{img.url}}" class="thumb-img" loading="lazy">
                        <span class="thumb-name">${{img.name}}</span>
                    `;
                    card.querySelector('img').onclick = () => showLightbox(img.url, img.name);
                    detailThumbs.appendChild(card);
                }});
            }}

            // 4. 渲染明细表格
            if (skuTableContent && data.skuData && data.skuData.skuMatrix) {{
                let tableHtml = '<table style="width:100%; border-collapse:collapse; font-size:12px; color:#e2e8f0;"><tr style="background:#334155; text-align:left;"><th style="padding:6px;">序号</th><th style="padding:6px;">规格属性</th><th style="padding:6px;">阶梯单价(元)</th><th style="padding:6px;">库存</th></tr>';
                data.skuData.skuMatrix.forEach((row, i) => {{
                    tableHtml += `<tr style="border-bottom:1px solid #334155;"><td style="padding:6px;">${{i+1}}</td><td style="padding:6px;">${{row.specAttributes}}</td><td style="padding:6px; color:#38bdf8;">${{row.price || '-'}}</td><td style="padding:6px; color:#4ade80;">${{row.stock || '-'}}</td></tr>`;
                }});
                tableHtml += '</table>';
                skuTableContent.innerHTML = tableHtml;
            }}

            // 5. 渲染 JSON
            if (skuJsonCode && data.skuData) {{
                skuJsonCode.textContent = JSON.stringify(data.skuData, null, 2);
            }}
        }};

        // 批量选择按钮事件
        wrapper.querySelectorAll('.btn-group-select-all').forEach(btn => {{
            btn.onclick = () => {{
                const target = btn.getAttribute('data-target');
                wrapper.querySelectorAll(`.thumb-checkbox[data-type="${{target}}"]`).forEach(cb => cb.checked = true);
            }};
        }});

        wrapper.querySelectorAll('.btn-group-clear-all').forEach(btn => {{
            btn.onclick = () => {{
                const target = btn.getAttribute('data-target');
                wrapper.querySelectorAll(`.thumb-checkbox[data-type="${{target}}"]`).forEach(cb => cb.checked = false);
            }};
        }});

        // SKU 大图/表格/画廊 Tab 切换
        const tabBtns = wrapper.querySelectorAll('.sku-tab-btn');
        tabBtns.forEach(btn => {{
            btn.onclick = () => {{
                tabBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const target = btn.getAttribute('data-tab');
                const contents = wrapper.querySelectorAll('.sku-tab-content');
                contents.forEach(c => c.classList.add('hidden'));
                const showEl = wrapper.querySelector('#sku-tab-content-' + target);
                if (showEl) showEl.classList.remove('hidden');
            }};
        }});

        // 重新扫描按钮
        if (scanBtn) {{
            scanBtn.onclick = () => {{
                if (statusArea) statusArea.classList.remove('hidden');
                if (statusText) statusText.textContent = '正在重新扫描页面素材...';
                setTimeout(() => {{
                    const d = runExtraction();
                    renderResults(d);
                }}, 300);
            }};
        }}

        // 下载按钮绑定
        if (btnDownload) {{
            btnDownload.onclick = async () => {{
                if (!currentData) return;
                btnDownload.disabled = true;
                btnDownload.textContent = '正在下载中...';
                if (progressArea) progressArea.classList.remove('hidden');
                if (progressBarFill) progressBarFill.style.width = '20%';
                if (progressText) progressText.textContent = '正在并发下载素材并生成配置...';

                // 收集选中的索引
                const selGallery = [];
                wrapper.querySelectorAll('.thumb-checkbox[data-type="gallery"]').forEach(cb => {{
                    if (cb.checked) selGallery.push(parseInt(cb.getAttribute('data-idx'), 10));
                }});

                const selSku = [];
                wrapper.querySelectorAll('.thumb-checkbox[data-type="sku"]').forEach(cb => {{
                    if (cb.checked) selSku.push(parseInt(cb.getAttribute('data-idx'), 10));
                }});

                const selDetail = [];
                wrapper.querySelectorAll('.thumb-checkbox[data-type="detail"]').forEach(cb => {{
                    if (cb.checked) selDetail.push(parseInt(cb.getAttribute('data-idx'), 10));
                }});

                const payload = {{
                    data: currentData,
                    selection: {{
                        gallery_indices: selGallery,
                        sku_indices: selSku,
                        detail_indices: selDetail,
                        sku_matrix_indices: Array.from(Array(currentData.skuData?.skuMatrix?.length || 0).keys())
                    }},
                    outputDir: "{default_output_dir}"
                }};

                try {{
                    let resStr = "";
                    if (window.__ag_py_download_assets) {{
                        resStr = await window.__ag_py_download_assets(JSON.stringify(payload));
                    }}
                    const res = resStr ? JSON.parse(resStr) : {{ success: true }};

                    if (progressBarFill) progressBarFill.style.width = '100%';
                    if (progressText) progressText.textContent = '✅ 全部素材下载完成！已保存到本地文件夹。';
                    btnDownload.textContent = '下载完成';
                    btnDownload.disabled = false;

                    if (res.outputDir) {{
                        savedDownloadDir = res.outputDir;
                        if (actionsSecondary) actionsSecondary.classList.remove('hidden');
                    }}
                }} catch (err) {{
                    if (progressText) progressText.textContent = '❌ 下载出错: ' + err.message;
                    btnDownload.textContent = '重试下载';
                    btnDownload.disabled = false;
                }}
            }};
        }}

        // 打开文件夹按钮绑定
        if (btnOpenFolder) {{
            btnOpenFolder.onclick = () => {{
                if (savedDownloadDir && window.__ag_py_open_folder) {{
                    window.__ag_py_open_folder(savedDownloadDir);
                }}
            }};
        }}

        // 初次加载自动执行一次
        const initData = runExtraction();
        if (initData) {{
            renderResults(initData);
        }}

        return true;
    }})();
    """

    try:
        page.evaluate(injection_script)
        return True
    except Exception as e:
        if log_fn:
            log_fn(f"Chrome 插件浮层注入异常: {str(e)}", "warn")
        return False
