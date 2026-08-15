// ==UserScript==
// @name         妙手SKU自动化录入(智能升级版)
// @description  自动解析维度并填充
// ==/UserScript==

(function() {
    // 清除旧面板
    const oldPanel = document.getElementById('miaoshou-sku-panel');
    if (oldPanel) oldPanel.remove();

    // 注入面板
    const panel = document.createElement('div');
    panel.id = 'miaoshou-sku-panel';
    panel.style.position = 'fixed';
    panel.style.top = '20px';
    panel.style.right = '20px';
    panel.style.zIndex = '999999';
    panel.style.backgroundColor = '#fff';
    panel.style.border = '1px solid #ccc';
    panel.style.padding = '15px';
    panel.style.boxShadow = '0 12px 32px rgba(0,0,0,0.12), 0 4px 12px rgba(0,0,0,0.08)';
    panel.style.borderRadius = '12px';
    panel.style.fontFamily = 'sans-serif';
    panel.style.width = '320px';
    
    const iconDataUrl = "data:image/png;base64,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";

    panel.innerHTML = `
        <div id="miaoshou-close-btn" style="position: absolute; top: 12px; right: 14px; cursor: pointer; font-size: 16px; color: #909399; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: #f4f4f5; transition: all 0.2s;">✕</div>
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
            <img src="${iconDataUrl}" style="width: 36px; height: 36px; border-radius: 8px; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.35);" />
            <div>
                <h3 style="margin: 0; font-size: 16px; color: #1e293b; font-weight: 700;">SKU 智能录入引擎</h3>
                <span style="font-size: 11px; color: #64748b; font-weight: 500;">妙手 AI 效率助手</span>
            </div>
        </div>
        <p style="font-size: 12px; color: #64748b; margin: 0 0 10px 0;">格式: 颜色-尺寸-编码-价格-库存-状况-平台sku-促销价-促销时间-[图片路径]</p>
        
        <div style="font-size: 12px; margin-bottom: 4px; font-weight: bold; color: #334155;">1. 选择数据文件 (.txt)</div>
        <input type="file" id="sku-file-input" accept=".txt,.csv" style="margin-bottom: 8px; width: 100%; box-sizing: border-box; font-size: 12px;" />

        <div style="font-size: 12px; margin-bottom: 4px; font-weight: bold; color: #334155;">2. 选择图片/图片文件夹 (纯前端直接读取)</div>
        <input type="file" id="sku-img-input" multiple accept="image/*" style="margin-bottom: 10px; width: 100%; box-sizing: border-box; font-size: 12px;" />

        <div id="sku-status" style="font-size: 12px; margin-bottom: 10px; color: #334155; background: #f8fafc; padding: 6px 8px; border-radius: 6px; border: 1px solid #e2e8f0; line-height: 1.4;">等待选择数据文件...</div>
        
        <button id="btn-start-auto" disabled style="padding: 10px 12px; background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: #fff; border: none; border-radius: 6px; cursor: pointer; width: 100%; font-weight: bold; font-size: 14px; box-shadow: 0 2px 6px rgba(16, 185, 129, 0.3); margin-bottom: 8px;">▶ 一键全自动执行 (变体 + 填充 + 图片)</button>

        <button id="btn-upload-images" style="padding: 9px 12px; background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%); color: #fff; border: none; border-radius: 6px; cursor: pointer; width: 100%; font-weight: bold; font-size: 13px; box-shadow: 0 2px 6px rgba(99, 102, 241, 0.3);">📷 自动上传 SKU 图片 (点击+号选本地图片)</button>
    `;
    
    document.body.appendChild(panel);

    // 监听本地图片选择 (可选)
    const imgInput = panel.querySelector('#sku-img-input');
    if (imgInput) {
        imgInput.addEventListener('change', function(e) {
            const files = Array.from(e.target.files);
            files.forEach(f => {
                selectedImageFiles[f.name.toLowerCase()] = f;
            });
            console.log(`已加载 ${files.length} 个本地图片文件:`, Object.keys(selectedImageFiles));
            document.getElementById('sku-status').innerHTML += `<br>📷 已加载 ${files.length} 张本地图片文件`;
        });
    }

    // 监听【自动上传 SKU 图片】按钮点击
    const btnUploadImages = panel.querySelector('#btn-upload-images');
    if (btnUploadImages) {
        btnUploadImages.addEventListener('click', async function() {
            const btn = this;
            btn.disabled = true;
            const originalText = btn.textContent;
            btn.textContent = "正在准备上传图片...";

            try {
                let dataToUse = parsedData;
                // 如果用户还没解析 txt 文件，默认使用第一个 SKU（红色-S）测试
                if (!dataToUse || dataToUse.length === 0) {
                    console.log("未解析数据文件，默认连续上传 5 张测试图片");
                    dataToUse = [
                        { color: '红色', size: 'S', code: 'C01', imageName: 'D:\\\\myCoding\\\\skuAddBatch\\\\test_images\\\\red_s.jpg' },
                        { color: '蓝色', size: 'S', code: 'C02', imageName: 'D:\\\\myCoding\\\\skuAddBatch\\\\test_images\\\\blue_s.jpg' },
                        { color: '黑色', size: 'M', code: 'C03', imageName: 'D:\\\\myCoding\\\\skuAddBatch\\\\test_images\\\\black_m.jpg' },
                        { color: '绿色', size: 'S', code: 'C04', imageName: 'D:\\\\myCoding\\\\skuAddBatch\\\\test_images\\\\green_s.jpg' },
                        { color: '黄色', size: 'S', code: 'C05', imageName: 'D:\\\\myCoding\\\\skuAddBatch\\\\test_images\\\\yellow_s.jpg' }
                    ];
                }

                document.getElementById('sku-status').innerHTML = `📷 正在定位图片区域，点击【+】号选择本地图片 (${dataToUse.length} 项)...`;

                // 清理所有已有图片
                document.getElementById('sku-status').innerHTML = `📷 正在清理页面已有图片...`;
                await clearAllImages();

                let successCount = 0;
                for (let idx = 0; idx < dataToUse.length; idx++) {
                    const item = dataToUse[idx];
                    document.getElementById('sku-status').innerHTML = `📷 正在自动上传 [${item.color}-${item.size}] 图片...`;
                    const ok = await uploadSingleSkuImage(item, idx);
                    if (ok) successCount++;
                    await new Promise(r => setTimeout(r, 600));
                }

                document.getElementById('sku-status').innerHTML = `✅ 图片上传完成！已处理 ${successCount} / ${dataToUse.length} 张图片`;
                alert(`✅ 成功自动点击【+】号并上传了 ${successCount} 张 SKU 图片！`);
            } catch (err) {
                console.error("上传图片异常:", err);
                alert("上传过程出错，请检查控制台：" + err.message);
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        });
    }


    // 监听关闭按钮
    panel.querySelector('#miaoshou-close-btn').addEventListener('click', function() {
        panel.remove();
    });
    
    
    // 捕获全局未处理的 Promise 异常以排查问题
    if (!window._miaoshouErrCatcherInjected) {
        window.addEventListener('unhandledrejection', function(event) {
            console.error("【捕捉到未处理的 Promise 拒绝】", event.reason);
            if (event.reason) {
                console.error(JSON.stringify(event.reason, Object.getOwnPropertyNames(event.reason)));
            }
        });
        window._miaoshouErrCatcherInjected = true;
    }

    let parsedData = [];
    let uniqueColors = [];
    let uniqueSizes = [];
    
    // 全局图片文件存储
    let selectedImageFiles = {};

    let skuMetadata = {
        baseDir: '',
        productDir: '',
        mainImage: '',
        detailDir: '',
        skuDir: '',
        header: []
    };

    // 当前待上传的文件引用（供上传流程内部使用）
    let targetFileForUpload = null;

    // 颜色中文到英文文件名前缀的映射字典
    const COLOR_MAP = {
        '红色': 'red', '蓝色': 'blue', '黑色': 'black', '白色': 'white', '黄色': 'yellow', '绿色': 'green',
        '红': 'red', '蓝': 'blue', '黑': 'black', '白': 'white', '黄': 'yellow', '绿': 'green'
    };

    function getExpectedFilename(color, size) {
        const c = COLOR_MAP[color] || (color || '').toLowerCase();
        const s = (size || '').toLowerCase();
        return `${c}_${s}.jpg`;
    }

    function resolveImagePath(imagePathStr, color, size) {
        if (skuMetadata.baseDir && skuMetadata.productDir && skuMetadata.skuDir) {
            let cleanBase = skuMetadata.baseDir.replace(/\\/g, '/').replace(/\/$/, '');
            let cleanImageName = imagePathStr || getExpectedFilename(color, size);
            return `${cleanBase}/${skuMetadata.productDir}/${skuMetadata.skuDir}/${cleanImageName}`;
        }
        
        const expected = getExpectedFilename(color, size);
        if (!imagePathStr) return expected;
        let clean = imagePathStr.replace(/\\/g, '/').trim();
        if (/\.(jpg|jpeg|png|webp|gif)$/i.test(clean)) {
            return clean;
        }
        if (!clean.endsWith('/')) clean += '/';
        return clean + expected;
    }

    function showImagePreviewDialog(file) {
        return new Promise((resolve) => {
            const url = URL.createObjectURL(file);
            const overlay = document.createElement('div');
            overlay.style.cssText = 'position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.6); z-index:999999; display:flex; justify-content:center; align-items:center;';
            
            const dialog = document.createElement('div');
            dialog.style.cssText = 'background:#fff; padding:20px; border-radius:12px; text-align:center; max-width: 400px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); font-family: sans-serif;';
            
            dialog.innerHTML = `
                <h3 style="margin-top:0; color:#333; font-size:18px;">✅ 成功在内存中读取到图片</h3>
                <p style="color:#666; font-size:14px; margin-bottom:15px; word-break: break-all;">文件名: <b>${file.name}</b><br>大小: ${(file.size/1024).toFixed(1)} KB<br>类型: ${file.type}</p>
                <div style="background:#f8fafc; padding:10px; border-radius:8px; margin-bottom:20px;">
                    <img src="${url}" style="max-width:100%; max-height:250px; border-radius:4px; object-fit: contain;" />
                </div>
                <button id="close-preview-btn" style="padding:10px 24px; background:linear-gradient(135deg, #6366f1, #4f46e5); color:white; border:none; border-radius:6px; cursor:pointer; font-weight:bold; font-size:15px; width: 100%;">关闭预览，继续执行上传</button>
            `;
            
            overlay.appendChild(dialog);
            document.body.appendChild(overlay);
            
            dialog.querySelector('#close-preview-btn').addEventListener('click', () => {
                document.body.removeChild(overlay);
                URL.revokeObjectURL(url);
                resolve();
            });
        });
    }

    async function getFileForSku(item) {
        const expectedName = getExpectedFilename(item.color, item.size);
        
        // 1. 优先从网页手动选择的图片内存中匹配
        if (selectedImageFiles[expectedName.toLowerCase()]) {
            return selectedImageFiles[expectedName.toLowerCase()];
        }
        const keys = Object.keys(selectedImageFiles);
        const colorNameEng = COLOR_MAP[item.color] || item.color;
        const matchedKey = keys.find(k => k.includes(colorNameEng) && k.includes((item.size || '').toLowerCase()));
        if (matchedKey) {
            return selectedImageFiles[matchedKey];
        }

        // 2. 突破 HTTPS 限制：优先向插件 Background 进程发送消息抓取图片 (无 Mixed Content 阻挡)
        const fullPath = resolveImagePath(item.imageName, item.color, item.size);
        if (typeof chrome !== 'undefined' && chrome.runtime && chrome.runtime.sendMessage) {
            try {
                const bgRes = await new Promise((resolve) => {
                    chrome.runtime.sendMessage({ type: 'FETCH_IMAGE', path: fullPath }, (res) => resolve(res));
                });
                if (bgRes && bgRes.success && bgRes.dataUrl) {
                    const res = await fetch(bgRes.dataUrl);
                    const blob = await res.blob();
                    const filename = fullPath.split('/').pop() || expectedName;
                    return new File([blob], filename, { type: bgRes.type || 'image/jpeg' });
                }
            } catch (e) {
                console.warn("通过 Background 获取图片异常，尝试直接 fetch:", e);
            }
        }

        // 3. 降级防护：直接向本地 HTTP 服务 (http://localhost:31415) 请求
        try {
            const imgUrl = 'http://localhost:31415/?path=' + encodeURIComponent(fullPath);
            const res = await fetch(imgUrl);
            if (res.ok) {
                const blob = await res.blob();
                const filename = fullPath.split('/').pop() || expectedName;
                return new File([blob], filename, { type: blob.type || 'image/jpeg' });
            }
        } catch (err) {
            console.warn("无法从本地服务获取图片: " + fullPath, err);
        }
        
        return null;
    }


    async function clearAllImages() {
        console.log("正在自动清理产品图片和 SKU 图片区域已上传的图片...");
        const deleteBtns = Array.from(document.querySelectorAll('.product-picture-list .shopee-icon-shanchu, .picture-draggable-list .shopee-icon-shanchu, .picture-table-list .shopee-icon-shanchu, .upload-container .shopee-icon-shanchu'));
        
        let clearedCount = 0;
        for (let btn of deleteBtns) {
            try {
                ['mousedown', 'mouseup', 'click'].forEach(evt => {
                    btn.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                });
                if (typeof btn.click === 'function') btn.click();
                clearedCount++;
                await new Promise(r => setTimeout(r, 150));
            } catch(e) {}
        }
        console.log(`清理完毕，共删除了 ${clearedCount} 张图片`);
    }

    // 在 SKU 图片表格（picture-table-list）中定位指定变体所在行。
    // 匹配优先级：变体名 > 颜色+尺寸文本 > 行索引。
    function findSkuPictureRow(item, rowIndex) {
        const table = document.querySelector('.picture-table-list');
        if (!table) return null;
        const rows = Array.from(table.querySelectorAll('.pro-virtual-table__row'));
        if (rows.length === 0) return null;

        // 1. 优先用变体名（产品名）匹配 —— SKU选项列的文本
        if (item.variantName) {
            const byName = rows.find(r => r.textContent.includes(item.variantName));
            if (byName) return byName;
        }

        // 2. 用颜色+尺寸文本匹配（部分页面变体名含颜色/尺寸）
        const byColor = rows.find(r => r.textContent.includes(item.color) && r.textContent.includes(item.size));
        if (byColor) return byColor;

        // 3. 按行索引匹配（表格行顺序与变体生成顺序一致）
        if (typeof rowIndex === 'number' && rowIndex >= 0 && rowIndex < rows.length) {
            return rows[rowIndex];
        }

        return null;
    }

    // 从一行中提取"图片"列（第2个 row-cell，列头为"图片"，区别于"Swatch Image"列）。
    // 返回该列的根 cell 元素；找不到时返回 null。
    function findPictureCellInRow(row) {
        const cells = Array.from(row.querySelectorAll('.pro-virtual-table__row-cell'));
        if (cells.length === 0) return null;
        // 列结构: [0]=SKU选项 [1]=图片 [2]=Swatch Image
        // "图片"列宽度自适应(flex:1 1 0%)，Swatch 列固定宽度(flex:0 0 200px)
        // 优先取索引1；若列数不足则取含 add-image-box 且 footer 文本为"添加新图片"的 cell
        if (cells.length >= 2) return cells[1];

        // 降级：找含 "添加新图片" 的 cell
        const cellWithAdd = cells.find(c => c.textContent.includes('添加新图片'));
        return cellWithAdd || cells[0];
    }

    // 拦截 Vue/React 动态创建的 input[type=file] 并注入文件。
    // 妙手平台点击上传按钮后，框架内部会创建 input[type=file] 并立即调用 .click()，
    // 然后移除该 input。我们需要在这个 input 出现的瞬间注入文件并触发 change。
    function interceptFileInput(file, timeoutMs) {
        return new Promise((resolve) => {
            let resolved = false;
            const finish = (success, msg) => {
                if (resolved) return;
                resolved = true;
                observer.disconnect();
                clearTimeout(timer);
                console.log(`[文件拦截] ${success ? '成功' : '失败'}: ${msg}`);
                resolve(success);
            };

            // 监听整个 document 的子树变化
            const observer = new MutationObserver((mutations) => {
                for (const mut of mutations) {
                    for (const node of mut.addedNodes) {
                        if (node.nodeType !== 1) continue;
                        // 检查新增节点本身或其子节点是否为 input[type=file]
                        const fileInput = node.tagName === 'INPUT' && node.type === 'file'
                            ? node
                            : node.querySelector && node.querySelector('input[type="file"]');
                        if (fileInput && fileInput.id !== 'sku-file-input' && fileInput.id !== 'sku-img-input') {
                            // 拦截到了！注入文件
                            injectFileToInput(fileInput, file);
                            finish(true, `已向动态创建的 input 注入文件: ${file.name}`);
                            return;
                        }
                    }
                }
            });
            observer.observe(document.documentElement, { childList: true, subtree: true });

            const timer = setTimeout(() => {
                // 超时降级：尝试在现有 input 中找目标
                const existing = Array.from(document.querySelectorAll('input[type="file"]')).filter(
                    i => i.id !== 'sku-file-input' && i.id !== 'sku-img-input'
                );
                if (existing.length > 0) {
                    const last = existing[existing.length - 1];
                    injectFileToInput(last, file);
                    finish(true, `超时降级：向最后一个现有 input 注入文件: ${file.name}`);
                } else {
                    finish(false, `超时 ${timeoutMs}ms 未捕获到 input[type=file]`);
                }
            }, timeoutMs || 3000);
        });
    }

    // 向 input 注入文件并触发 Vue/React 的 change 事件
    function injectFileToInput(input, file) {
        try {
            const dt = new DataTransfer();
            dt.items.add(file);
            // 直接赋值 files 属性
            input.files = dt.files;
            // 如果赋值失败（Vue 拦截了 setter），用 Object.defineProperty 强制覆写
            if (!input.files || input.files.length === 0) {
                Object.defineProperty(input, 'files', {
                    value: dt.files,
                    writable: false,
                    configurable: true
                });
            }
        } catch (e) {
            console.error('[文件注入] files 赋值异常:', e);
        }
        // 触发完整事件链，确保 Vue/React 双向绑定更新
        input.dispatchEvent(new Event('input', { bubbles: true, cancelable: true }));
        input.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
        input.dispatchEvent(new Event('blur', { bubbles: true, cancelable: true }));
        // 同时向父级容器派发 change（部分框架监听父级）
        const parent = input.closest('.el-upload, .jx-upload, .upload-card, .add-image-box, .jx-dropdown-menu__item, .picture-selector-item, .picture-draggable-list');
        if (parent) {
            parent.dispatchEvent(new Event('change', { bubbles: true, cancelable: true }));
        }
        console.log(`[文件注入] 已向 input 注入 ${file.name} 并触发事件`, input);
    }

    async function uploadSingleSkuImage(item, rowIndex) {
        const file = await getFileForSku(item);
        if (!file) {
            console.warn(`未找到 [${item.color}-${item.size}] 对应的本地图片文件`);
            return false;
        }

        file.uid = Date.now() + Math.floor(Math.random() * 1000);
        console.log(`准备自动上传 [${item.color}-${item.size}] 图片与Swatch: ${file.name}`);

        // 定位 SKU 图片表格中的目标行
        const targetRow = findSkuPictureRow(item, rowIndex);
        if (!targetRow) {
            console.warn(`未在 SKU 图片表格中找到 [${item.color}-${item.size}] 对应的行`);
            return false;
        }
        console.log(`已定位到 [${item.color}-${item.size}] 的 SKU 图片行`, targetRow);

        async function doUpload(scope, typeName) {
            const selectors = '.add-image-box, .arco-upload, .upload-icon, [class*="upload-box"], [class*="upload-btn"], [class*="UploadBtn"], .pro-upload, [class*="upload"], [class*="swatch"]';
            let uploadBtns = Array.from(scope.querySelectorAll(selectors));
            
            if (uploadBtns.length === 0 && scope === targetRow) {
                uploadBtns = Array.from(targetRow.querySelectorAll('*')).filter(b => {
                    const cell = b.closest('.pro-virtual-table__row-cell');
                    const txt = b.textContent || '';
                    return cell && (txt.includes('添加新图片') || txt.includes('Upload'));
                });
            }
            if (uploadBtns.length === 0) {
                uploadBtns = Array.from(scope.querySelectorAll(selectors));
            }
            // 兜底：寻找带有加号或者上传提示的任意元素
            if (uploadBtns.length === 0) {
                uploadBtns = Array.from(scope.querySelectorAll('div, span, button, i, svg')).filter(b => {
                    if (b.tagName === 'INPUT') return false;
                    const className = (b.className && typeof b.className === 'string') ? b.className.toLowerCase() : '';
                    return className.includes('upload') || className.includes('add') || className.includes('plus') || className.includes('icon') || className.includes('swatch');
                });
            }
            uploadBtns = uploadBtns.filter((btn, index, self) => {
                return !self.some((other, otherIndex) => index !== otherIndex && other.contains(btn));
            });

            if (uploadBtns.length === 0) {
                console.warn(`[${item.color}-${item.size}] 的 ${typeName} 列未找到上传按钮`);
                return false;
            }

            console.log(`找到 [${item.color}-${item.size}] ${typeName} 列的上传按钮，准备触发上传...`);
            const btn = uploadBtns[0];
            const interceptPromise = interceptFileInput(file, 4000);
            
            targetFileForUpload = file;
            ['mousedown', 'mouseup', 'click'].forEach(evt => {
                btn.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
            });
            if (typeof btn.click === 'function') btn.click();
            
            const success = await interceptPromise;
            targetFileForUpload = null;
            
            if (success) {
                await new Promise(r => setTimeout(r, 1200));
                console.log(`[${item.color}-${item.size}] ${typeName} 图片上传完成`);
                return true;
            } else {
                console.warn(`[${item.color}-${item.size}] ${typeName} 图片上传失败：未捕获到 file input`);
                return false;
            }
        }

        const pictureCell = findPictureCellInRow(targetRow);
        const scope = pictureCell || targetRow;
        
        // 1. 上传 Swatch Image 列 (主图第1张)
        let successSwatch = true;
        const cells = Array.from(targetRow.querySelectorAll('.pro-virtual-table__row-cell'));
        if (cells.length >= 3) {
            const swatchCell = cells[2];
            successSwatch = await doUpload(swatchCell, 'Swatch');
            await new Promise(r => setTimeout(r, 300));
        }

        // 2. 上传 图片 列 (主图)
        const successPicture = await doUpload(scope, '图片');

        return successPicture || successSwatch;
    }

    // 辅助函数：模拟 Vue 输入
    function setNativeValue(element, value) {
        if (!element) return;
        
        let valueSetter = Object.getOwnPropertyDescriptor(element, 'value')?.set;
        let prototype = Object.getPrototypeOf(element);
        let prototypeValueSetter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
        
        if (prototypeValueSetter && valueSetter !== prototypeValueSetter) {
            prototypeValueSetter.call(element, value);
        } else if (valueSetter) {
            valueSetter.call(element, value);
        } else {
            element.value = value; // Fallback
        }
        
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // 监听文件选择
    panel.querySelector('#sku-file-input').addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (!file) return;
        
        const reader = new FileReader();
        reader.onload = function(e) {
            const content = e.target.result;
            const lines = content.split('\n').map(s => s.trim()).filter(s => s !== '');
            parsedData = [];
            let colorsSet = new Set();
            let sizesSet = new Set();

            if (lines.length > 6) {
                skuMetadata.baseDir = lines[0];
                skuMetadata.productDir = lines[1];
                skuMetadata.mainImage = lines[2];
                skuMetadata.detailDir = lines[3];
                skuMetadata.skuDir = lines[4];
                skuMetadata.header = lines[5].split('"-"').map(s => s.replace(/"/g, ''));
                
                // 从第7行（索引为6）开始取数据
                const dataLines = lines.slice(6);
                dataLines.forEach(line => {
                    let cleanLine = line.trim();
                    if (cleanLine.startsWith('"') && cleanLine.endsWith('"')) {
                        cleanLine = cleanLine.substring(1, cleanLine.length - 1);
                    }
                    
                    const parts = cleanLine.split('"-"');
                    if(parts.length >= 10) {
                        let color = parts[1]; // 第2列是颜色
                        let size = parts[2];  // 第3列是尺寸
                        parsedData.push({
                            imageName: parts[0],
                            color: color,
                            size: size,
                            code: parts[3],
                            price: parts[4],
                            stock: parts[5],
                            condition: parts[6],
                            platformSku: parts[7],
                            promoPrice: parts[8],
                            promoTime: parts[9] || ''
                        });
                        colorsSet.add(color);
                        sizesSet.add(size);
                    }
                });
            } else {
                alert('数据文件格式不正确，缺少前6行配置信息！');
            }

            uniqueColors = Array.from(colorsSet);
            uniqueSizes = Array.from(sizesSet);

            document.getElementById('sku-status').innerHTML = 
                `解析成功! 共 <b>${parsedData.length}</b> 行数据。<br>` +
                `🎨 颜色 (${uniqueColors.length}): ${uniqueColors.join(', ')}<br>` +
                `📏 尺寸 (${uniqueSizes.length}): ${uniqueSizes.join(', ')}`;
                
            document.getElementById('btn-start-auto').disabled = false;
        };
        reader.readAsText(file);
    });

    // 监听自动添加变体维度

    panel.querySelector('#btn-start-auto').addEventListener('click', async function() {
        const btn = this;
        btn.disabled = true;
        btn.textContent = "正在自动处理中，请不要乱动...";
        
        try {
            document.getElementById('sku-status').innerHTML = '步骤 1/4: 正在全面深度清理现有数据...';
            
            // ================= 步骤 1：深度清理 =================
            // 清理变体属性
            const tempFormItems = Array.from(document.querySelectorAll('.sale-attribute-list .jx-form-item'));
            const tempColorItem = tempFormItems.find(item => item.querySelector('.jx-form-item__label') && item.querySelector('.jx-form-item__label').textContent.includes('颜色'));
            const tempSizeItem = tempFormItems.find(item => item.querySelector('.jx-form-item__label') && (item.querySelector('.jx-form-item__label').textContent.includes('尺寸') || item.querySelector('.jx-form-item__label').textContent.includes('尺码')));
            
            if (tempColorItem) {
                let deleteBtns = Array.from(tempColorItem.querySelectorAll('.delete-icon'));
                for (let db of deleteBtns) { db.click(); await new Promise(r => setTimeout(r, 100)); }
            }
            if (tempSizeItem) {
                let deleteBtns = Array.from(tempSizeItem.querySelectorAll('.delete-icon'));
                for (let db of deleteBtns) { db.click(); await new Promise(r => setTimeout(r, 100)); }
            }
            
            // 清理图片
            if (typeof clearAllImages === 'function') {
                await clearAllImages();
            }
            
            // 如果 parsedData 为空，使用默认测试数据
            if (!parsedData || parsedData.length === 0) {
                console.log("未解析数据文件，默认连续上传 5 张测试图片");
                parsedData = [
                    { color: '红色', size: 'S', code: 'C01', imageName: 'D:\\myCoding\\skuAddBatch\\test_images\\red_s.jpg' },
                    { color: '蓝色', size: 'S', code: 'C02', imageName: 'D:\\myCoding\\skuAddBatch\\test_images\\blue_s.jpg' },
                    { color: '黑色', size: 'M', code: 'C03', imageName: 'D:\\myCoding\\skuAddBatch\\test_images\\black_m.jpg' },
                    { color: '绿色', size: 'S', code: 'C04', imageName: 'D:\\myCoding\\skuAddBatch\\test_images\\green_s.jpg' },
                    { color: '黄色', size: 'S', code: 'C05', imageName: 'D:\\myCoding\\skuAddBatch\\test_images\\yellow_s.jpg' }
                ];
                let colorsSet = new Set(parsedData.map(d => d.color));
                let sizesSet = new Set(parsedData.map(d => d.size));
                uniqueColors = Array.from(colorsSet);
                uniqueSizes = Array.from(sizesSet);
            }

            // ================= 步骤 2：添加并填入变体维度 =================
            document.getElementById('sku-status').innerHTML = '步骤 2/4: 正在添加【变体维度】...';
            
            const formItems = Array.from(document.querySelectorAll('.sale-attribute-list .jx-form-item'));
            const colorItem = formItems.find(item => {
                const label = item.querySelector('.jx-form-item__label');
                return label && label.textContent.includes('颜色');
            });
            const sizeItem = formItems.find(item => {
                const label = item.querySelector('.jx-form-item__label');
                return label && (label.textContent.includes('尺寸') || label.textContent.includes('尺码'));
            });
            
            async function fillAttribute(item, values) {
                if (!item || !values || values.length === 0) return;
                
                // 清除现有
                let deleteBtns = Array.from(item.querySelectorAll('.delete-icon'));
                for (let db of deleteBtns) {
                    db.click();
                    await new Promise(r => setTimeout(r, 100));
                }
                
                // 逐个添加
                const addBtn = Array.from(item.querySelectorAll('button')).find(b => b.textContent.includes('添加选项'));
                
                for (let i = 0; i < values.length; i++) {
                    let inputs = Array.from(item.querySelectorAll('input[type="text"]'));
                    
                    // 【关键修复】如果当前需要的输入框索引超出了页面现有的输入框数量，直接点击添加选项
                    if (i >= inputs.length && addBtn) {
                        addBtn.click();
                        await new Promise(r => setTimeout(r, 200));
                        inputs = Array.from(item.querySelectorAll('input[type="text"]'));
                    }
                    
                    const inputToFill = inputs[i];
                    if (inputToFill) {
                        inputToFill.focus();
                        
                        const selectWrapper = inputToFill.closest('.jx-select, .el-select');
                        if (selectWrapper) {
                            selectWrapper.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                            selectWrapper.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                            selectWrapper.click();
                        }
                        
                        setNativeValue(inputToFill, values[i]);
                        inputToFill.dispatchEvent(new Event('input', { bubbles: true }));
                        
                        await new Promise(r => setTimeout(r, 300));
                        
                        let clickedDropdown = false;
                        if (selectWrapper) {
                            const allItems = Array.from(document.querySelectorAll('.jx-select-dropdown__item, .el-select-dropdown__item, .jx-dropdown-menu__item, .el-select-dropdown li, .jx-select-dropdown li'));
                            const visibleItems = allItems.filter(el => {
                                const rect = el.getBoundingClientRect();
                                return rect.width > 0 && rect.height > 0;
                            });
                            const exactItem = visibleItems.find(el => el.textContent.trim() === values[i]);
                            if (exactItem) {
                                exactItem.click();
                                clickedDropdown = true;
                            }
                        }
                        
                        if (!clickedDropdown) {
                            inputToFill.dispatchEvent(new Event('change', { bubbles: true }));
                            const enterParams = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true };
                            inputToFill.dispatchEvent(new KeyboardEvent('keydown', enterParams));
                            inputToFill.dispatchEvent(new KeyboardEvent('keypress', enterParams));
                            inputToFill.dispatchEvent(new KeyboardEvent('keyup', enterParams));
                            inputToFill.blur();
                        }
                        
                        await new Promise(r => setTimeout(r, 200));
                    }
                }
            }

            if (colorItem) await fillAttribute(colorItem, uniqueColors);
            if (sizeItem) await fillAttribute(sizeItem, uniqueSizes);
            
            document.getElementById('sku-status').innerHTML = '步骤 3/4: 尝试确认提示框并等待表格生成...';
            
            // 循环等待（最长30秒），并尝试自动点击弹出框的“确认”按钮
            for (let i = 0; i < 60; i++) {
                // 尝试找寻网页中可能存在的确认按钮（比如 el-message-box__btns 的主按钮，或是带有“确 定”、“保存”字样的按钮）
                const confirmBtns = Array.from(document.querySelectorAll('.el-message-box__btns button.el-button--primary, .jx-dialog__footer button.jx-button--primary, .el-dialog__footer button.el-button--primary'));
                for (let cBtn of confirmBtns) {
                    if (cBtn.offsetParent !== null) { // 元素可见
                        cBtn.click();
                        console.log("自动点击了确认弹窗");
                    }
                }
                
                // 等待表格出现，且行数大于0
                const curRows = document.querySelectorAll('.pro-virtual-table__row');
                if (curRows.length > 0) {
                    // 多等1秒，确保 Vue 完全渲染完成并且图片上传按钮挂载好了
                    await new Promise(r => setTimeout(r, 1000));
                    break;
                }
                await new Promise(r => setTimeout(r, 500));
            }
            
            document.getElementById('sku-status').innerHTML = '步骤 4/4: 正在自动填充表格与上传图片...';
            await startFillingLogic();
            
            document.getElementById('sku-status').innerHTML = '✅ 全自动提效完成！';
            
        } catch (err) {
            console.error(err);
            alert("发生异常，请检查控制台。");
        } finally {
            btn.disabled = false;
            btn.textContent = "▶ 一键全自动执行 (变体 + 填充)";
        }
    });

    // 辅助：按 placeholder 查找 input

    function fillInputByPlaceholder(row, placeholderSnippet, value) {
        if (!value) return;
        const input = Array.from(row.querySelectorAll('input')).find(i => i.placeholder && i.placeholder.includes(placeholderSnippet));
        if (input) setNativeValue(input, value);
    }

    // 监听填充表格
    async function startFillingLogic() {
        const rows = Array.from(document.querySelectorAll('.pro-virtual-table__row'));
        let filledCount = 0;

        // 禁用按钮防连点
        const startBtn = document.getElementById('btn-start-auto');
        if (startBtn) startBtn.disabled = true;

        let totalFilled = 0;
        let lastScrollTop = -1;
        let stuckCount = 0;
        
        // 记录哪些数据已经填过了
        let processedMatches = new Set();

        while (true) {
            let processedInThisBatch = true;
            let currentBatchFilled = 0;

            // 循环处理，每次填完一行立刻中断并重新获取最新 DOM
            while (processedInThisBatch) {
                processedInThisBatch = false;
                const rows = Array.from(document.querySelectorAll('.pro-virtual-table__row'));
                
                for (let row of rows) {
                    const rowText = row.innerText;
                    
                    const possibleMatches = parsedData.filter(d => rowText.includes(d.color) && rowText.includes(d.size));
                    possibleMatches.sort((a, b) => b.size.length - a.size.length);
                    const match = possibleMatches[0];
                    
                    if (!match || processedMatches.has(match)) continue;
                    
                    // 开始精确填入
                    fillInputByPlaceholder(row, '外部产品 ID', match.code);
                    fillInputByPlaceholder(row, '商品基本价格', match.price);
                    fillInputByPlaceholder(row, '商品数量', match.stock);
                    fillInputByPlaceholder(row, '提供平台SKU', match.platformSku);
                    fillInputByPlaceholder(row, '待售产品的价格', match.promoPrice);
                    
                    if (match.promoTime.includes('至')) {
                        const dates = match.promoTime.split('至');
                        fillInputByPlaceholder(row, '促销开始', dates[0].trim());
                        fillInputByPlaceholder(row, '促销结束', dates[1].trim());
                    }
                    
                    let conditionInput = null;
                    const selects = Array.from(row.querySelectorAll('.jx-select, .el-select'));
                    
                    for (let sel of selects) {
                        const text = sel.textContent || '';
                        if (text.includes('新') || text.includes('New') || text.includes('二手') || text.includes(match.condition)) {
                            conditionInput = sel.querySelector('input');
                            break;
                        }
                    }
                    
                    if (!conditionInput && selects.length > 0) {
                        const possibleSelects = selects.filter(sel => {
                            const text = sel.textContent || '';
                            return !text.includes('UPC') && !text.includes('EAN') && !text.includes('ASIN') && !text.includes('GTIN');
                        });
                        if (possibleSelects.length > 0) {
                            conditionInput = possibleSelects[possibleSelects.length - 1].querySelector('input');
                        } else {
                            conditionInput = selects[selects.length - 1].querySelector('input');
                        }
                    }
                    
                    if (conditionInput && match.condition) {
                        const selectContainer = conditionInput.closest('.jx-select, .el-select, .jx-input');
                        const targetToClick = selectContainer || conditionInput;
                        
                        targetToClick.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                        targetToClick.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                        targetToClick.click();
                        
                        conditionInput.focus();
                        setNativeValue(conditionInput, match.condition);
                        
                        await new Promise(r => setTimeout(r, 500));
                        
                        const allItems = Array.from(document.querySelectorAll('.jx-select-dropdown__item, .el-select-dropdown__item, .jx-dropdown-menu__item, .el-select-dropdown li, .jx-select-dropdown li'));
                        const visibleItems = allItems.filter(el => {
                            const rect = el.getBoundingClientRect();
                            return rect.width > 0 && rect.height > 0;
                        });
                        
                        const exactItem = visibleItems.find(el => el.textContent.trim() === match.condition);
                        
                        if (exactItem) {
                            exactItem.click(); 
                        } else {
                            const enterParams = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true };
                            conditionInput.dispatchEvent(new KeyboardEvent('keydown', enterParams));
                            conditionInput.blur();
                        }
                    }
                    
                    // ================= 新增：自动上传本行的图片与 Swatch =================
                    if (typeof uploadSingleSkuImage === 'function' && match.imageName) {
                        document.getElementById('sku-status').innerHTML = `步骤 4/4: 正在填充 ${match.color}-${match.size} 并上传图片...`;
                        const matchIdx = parsedData.indexOf(match);
                        await uploadSingleSkuImage(match, matchIdx);
                        
                        // Swatch Image: 目前依靠平台本身的同源逻辑或 `uploadSingleSkuImage` 扩展后续支持。
                        // 如果有明确的 Swatch Button 也可以在 `uploadSingleSkuImage` 中统一处理。
                    }
                    // ================================================================

                    currentBatchFilled++;
                    await new Promise(r => setTimeout(r, 100));
                    
                    processedMatches.add(match);
                    
                    // 打断 for 循环，重新 querySelectorAll，避免 Vue 重绘导致的旧 DOM 失效
                    processedInThisBatch = true;
                    break;
                }
            }

            totalFilled += currentBatchFilled;

            // 尝试寻找滚动容器
            let scrollContainer = null;
            if (rows.length > 0) {
                let el = rows[0].parentElement;
                while (el && el !== document.body) {
                    if (el.classList.contains('jx-scrollbar__wrap') || el.classList.contains('pro-virtual-table__body-wrapper')) {
                        scrollContainer = el;
                        break;
                    }
                    const style = window.getComputedStyle(el);
                    if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                        scrollContainer = el;
                        break;
                    }
                    el = el.parentElement;
                }
            }

            if (scrollContainer) {
                // 如果滚动条位置没有改变，说明到底了
                if (Math.abs(scrollContainer.scrollTop - lastScrollTop) <= 2) {
                    stuckCount++;
                    if (stuckCount >= 2) break; // 连续两次没滚下去就结束
                } else {
                    stuckCount = 0;
                }
                lastScrollTop = scrollContainer.scrollTop;
                
                // 向下滚动一个屏幕的高度
                scrollContainer.scrollTop += scrollContainer.clientHeight - 100; // 留一点重叠余量
                
                // 重点：等待网页渲染新的虚拟表格行
                await new Promise(r => setTimeout(r, 1000));
            } else {
                // 如果实在找不到滚动容器，就只执行当前能看到的行
                break;
            }
        }

        //
        //
        alert(`✅ 自动翻页扫描完毕！共成功匹配并填入了 ${totalFilled} 行数据！`);
    }

})();
