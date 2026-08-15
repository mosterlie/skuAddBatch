"""
妙手 SKU 自动化执行引擎
负责调度变体生成、图片原生批量上传、虚拟表格滚动匹配与字段填入
"""
import os
import sys
import time
from typing import Optional, Callable, Set, List, Dict, Any
from playwright.sync_api import Page, Locator, ElementHandle

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from core.parser import SkuDataBundle, SkuItem


class SkuExecutor:
    """自动化执行引擎"""

    def __init__(self, page: Page, bundle: SkuDataBundle, log_fn: Optional[Callable[[str, str], None]] = None):
        self.page = page
        self.bundle = bundle
        self.log_fn = log_fn or self._default_log
        self._is_cancelled = False

    def _default_log(self, message: str, level: str = "info"):
        prefix = "ℹ️" if level == "info" else ("✅" if level == "success" else ("⚠️" if level == "warn" else "❌"))
        print(f"[{time.strftime('%H:%M:%S')}] {prefix} {message}")

    def log(self, message: str, level: str = "info"):
        self.log_fn(message, level)

    def cancel(self):
        """取消当前正在执行的任务"""
        self._is_cancelled = True
        self.log("用户请求终止当前自动化任务", "warn")

    def _check_cancelled(self):
        if self._is_cancelled:
            raise InterruptedError("任务已被用户手动终止")

    # =========================================================================
    # 辅助方法：设置 input 原生值并触发 Vue / ElementUI 的响应式更新
    # =========================================================================
    def _set_input_value(self, locator: Locator, value: str):
        """通过 JavaScript 原生 setter 注入并触发 input / change 事件，确保 Vue 状态同步"""
        if not value:
            return
        js_code = """
        (el, val) => {
            el.focus();
            const lastValue = el.value;
            el.value = val;
            const event = new Event('input', { bubbles: true });
            // 兼容 React / Vue 2 & 3
            const tracker = el._valueTracker;
            if (tracker) {
                tracker.setValue(lastValue);
            }
            el.dispatchEvent(event);
            el.dispatchEvent(new Event('change', { bubbles: true }));
            el.dispatchEvent(new Event('blur', { bubbles: true }));
        }
        """
        try:
            locator.evaluate(js_code, value)
        except Exception:
            try:
                locator.fill(value)
            except Exception:
                pass

    def _fill_input_by_placeholder(self, row_locator: Locator, placeholder_snippet: str, value: str) -> bool:
        """在指定的行容器中，根据 placeholder 模糊匹配输入框并填入数据"""
        if not value:
            return False
        try:
            inputs = row_locator.locator(f"input[placeholder*='{placeholder_snippet}']")
            if inputs.count() > 0:
                target_input = inputs.first
                self._set_input_value(target_input, value)
                return True
        except Exception:
            pass
        return False

    # =========================================================================
    # 步骤 1：深度全量清理现有数据（循环排空直到 100% 干净）
    # =========================================================================
    def clean_existing_data(self) -> bool:
        """
        全量彻底清理：
        1. 循环清理多维度变体属性选项（颜色/尺寸/自定义属性标签），直到完全清空
        2. 循环清理产品主图、详情图、SKU图片表格已上传的全部旧图片，直到完全清空
        """
        self._check_cancelled()
        self.log("正在执行【数据清理】：正在彻底排空多维度变体选项与旧图片...", "info")
        try:
            # 1. 检查是否存在商品编辑表单区域
            has_area = self.page.evaluate("() => document.querySelectorAll('.sale-attribute-list, .basic-info-layout, .pro-virtual-table, .basic-layout-side, .product-picture-list, .picture-table-list').length > 0")
            if not has_area:
                self.log("⚠️ 当前页面未检测到商品编辑表单，请确保浏览器已打开妙手【商品编辑/发布】页面！", "warn")
                return False

            # 2. 异步轮询排空变体标签 (支持 Vue 动态 DOM 重渲染)
            js_wipe_variants = """
            async () => {
                let totalCleaned = 0;
                const maxRounds = 50;
                
                for (let round = 0; round < maxRounds; round++) {
                    const sel = [
                        '.sale-attribute-item .delete-icon',
                        '.sale-attribute-value-item .delete-icon',
                        '.sale-attribute-value-list .delete-icon',
                        '.sale-attribute-list .delete-icon',
                        '.sale-attribute-item button.delete-icon',
                        '.sale-attribute-value-item button',
                        '.jx-form-item .delete-icon',
                        'button.delete-icon',
                        '.jx-tag__close',
                        '.el-tag__close',
                        '.arco-tag-close-btn'
                    ];
                    
                    const deleteBtns = Array.from(document.querySelectorAll(sel.join(', '))).filter(btn => {
                        const rect = btn.getBoundingClientRect();
                        const style = window.getComputedStyle(btn);
                        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                    });

                    if (deleteBtns.length === 0) {
                        break;
                    }

                    // 每次点击第一个，等待 Vue 响应后再继续寻找，避免 DOM 引用失效
                    const btn = deleteBtns[0];
                    try {
                        ['mousedown', 'mouseup', 'click'].forEach(evt => {
                            btn.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                        });
                        if (typeof btn.click === 'function') btn.click();
                        totalCleaned++;
                    } catch(e) {}

                    await new Promise(r => setTimeout(r, 60));
                }
                return totalCleaned;
            }
            """
            cleaned_vars = self.page.evaluate(js_wipe_variants)
            if cleaned_vars > 0:
                self.log(f"✅ 已全量清理 {cleaned_vars} 个多维度变体选项标签（已全部清空）", "info")
            else:
                self.log("ℹ️ 变体选项区域当前无残留标签", "info")

            # 3. 异步轮询排空所有图片
            cleaned_imgs = self.clean_existing_images()
            self.log("🎉【数据全量清空完成】多维度变体与全部已有图片已彻底清空干净！", "success")
            return True
        except Exception as e:
            self.log(f"清理数据时提示: {str(e)}", "warn")
            return True

    def clean_existing_images(self) -> int:
        """
        循环排空所有已上传图片（主图、详情图、SKU 变体图）
        """
        try:
            js_wipe_images = """
            async () => {
                let clearedCount = 0;
                const maxRounds = 60;
                const selectors = [
                    '.product-picture-list .shopee-icon-shanchu',
                    '.picture-draggable-list .shopee-icon-shanchu',
                    '.picture-table-list .shopee-icon-shanchu',
                    '.upload-container .shopee-icon-shanchu',
                    '.product-picture-list .delete-icon',
                    '.picture-draggable-list .delete-icon',
                    '.picture-table-list .delete-icon',
                    '.upload-container .delete-icon',
                    '.arco-upload-list-item-operation-delete',
                    '.picture-card-delete',
                    '.pro-picture__delete',
                    '.jx-upload-list__item-delete',
                    '.el-upload-list__item-delete',
                    '.image-item-delete',
                    '.product-picture-list i[class*="delete"]',
                    '.picture-table-list i[class*="delete"]'
                ];

                for (let round = 0; round < maxRounds; round++) {
                    const deleteBtns = Array.from(document.querySelectorAll(selectors.join(', '))).filter(btn => {
                        const rect = btn.getBoundingClientRect();
                        const style = window.getComputedStyle(btn);
                        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                    });

                    if (deleteBtns.length === 0) {
                        break;
                    }

                    const btn = deleteBtns[0];
                    try {
                        ['mousedown', 'mouseup', 'click'].forEach(evt => {
                            btn.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                        });
                        if (typeof btn.click === 'function') btn.click();
                        clearedCount++;
                    } catch(e) {}

                    await new Promise(r => setTimeout(r, 60));
                }
                return clearedCount;
            }
            """
            deleted_count = self.page.evaluate(js_wipe_images)
            if deleted_count > 0:
                self.log(f"✅ 已全量清理 {deleted_count} 张已上传图片 (主图/详情图/SKU图已全部清空)", "info")
            else:
                self.log("ℹ️ 图片区域当前无残留图片", "info")
            return deleted_count
        except Exception:
            return 0

    # =========================================================================
    # 步骤 2：自动添加变体维度 (颜色 / 尺寸)
    # =========================================================================
    def setup_variants(self) -> bool:
        """自动添加颜色与尺寸变体选项"""
        self._check_cancelled()
        self.log(f"正在执行【步骤 2/4】：添加变体维度 (颜色: {len(self.bundle.unique_colors)} 项, 尺寸: {len(self.bundle.unique_sizes)} 项)...", "info")

        try:
            form_items = self.page.locator(".jx-form-item, .sale-attribute-item, .el-form-item").all()
            color_item = None
            size_item = None

            for item in form_items:
                label_loc = item.locator(".jx-form-item__label, label, [class*='label']")
                if label_loc.count() > 0:
                    lbl = label_loc.first.inner_text()
                    if "颜色" in lbl and ("添加选项" in item.inner_text() or item.locator("button").count() > 0):
                        color_item = item
                    elif ("尺寸" in lbl or "尺码" in lbl) and ("添加选项" in item.inner_text() or item.locator("button").count() > 0):
                        size_item = item

            if not color_item and not size_item:
                self.log("⚠️ 未在页面中找到【颜色】或【尺寸】属性区域，请确认已打开商品编辑页并存在变体选项板块！", "warn")
                return False

            # 填充属性组
            if color_item and self.bundle.unique_colors:
                self._fill_single_attribute_group(color_item, self.bundle.unique_colors, "颜色")

            if size_item and self.bundle.unique_sizes:
                self._fill_single_attribute_group(size_item, self.bundle.unique_sizes, "尺寸")

            self.log("变体维度配置与生成完成！", "success")
            time.sleep(1.0)  # 等待虚拟表格生成
            return True
        except Exception as e:
            self.log(f"添加变体维度失败: {str(e)}", "warn")
            return False

    def _fill_single_attribute_group(self, group_item: Locator, values: List[str], group_name: str):
        """填充单个属性组（如全部颜色或全部尺寸，支持下拉菜单选择与自定义未命中回车填入两种模式）"""
        self.log(f"正在填充【{group_name}】列表: {', '.join(values)}", "info")

        for idx, val in enumerate(values):
            self._check_cancelled()

            # 使用 evaluate 在浏览器原生环境下精准添加与填入，支持标准 Input 和 Select-v2 下拉框
            js_fill_single = """
            async (args) => {
                const { groupName, targetIdx, targetVal } = args;
                const formItems = Array.from(document.querySelectorAll('.jx-form-item, .pro-form-item, .sale-attribute-item'));
                const group = formItems.find(f => {
                    const label = f.querySelector('.jx-form-item__label, label, [class*="label"]');
                    const labelText = label ? label.innerText.trim() : '';
                    const isTargetLabel = labelText.startsWith(groupName) || labelText.includes(groupName);
                    const notSpecType = !labelText.includes('规格类型') && !labelText.includes('主题');
                    return isTargetLabel && notSpecType && (f.innerText.includes('添加选项') || f.querySelectorAll('button').length > 0);
                });
                if (!group) return { success: false, msg: `未找到【${groupName}】表单行` };

                // 1. 获取现有输入框 (支持普通 input 和 textarea)
                let inputs = Array.from(group.querySelectorAll('.jx-input__inner, .jx-textarea__inner, .jx-select__input, input[type="text"], textarea, input:not([type="hidden"])'));

                // 2. 如果数量不够，点击添加选项
                const addBtn = Array.from(group.querySelectorAll('button')).find(b => b.innerText.includes('添加'));
                if (targetIdx >= inputs.length && addBtn) {
                    addBtn.scrollIntoView({ block: 'center' });
                    ['mousedown', 'mouseup', 'click'].forEach(evt => {
                        addBtn.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                    });
                    addBtn.click();
                    await new Promise(r => setTimeout(r, 200));
                    inputs = Array.from(group.querySelectorAll('.jx-input__inner, .jx-textarea__inner, .jx-select__input, input[type="text"], textarea, input:not([type="hidden"])'));
                }

                if (targetIdx >= inputs.length) {
                    return { success: false, msg: `第 ${targetIdx+1} 个输入框未成功生成` };
                }

                const input = inputs[targetIdx];
                const selectWrap = input.closest('.jx-select, .el-select, .pro-select-v2, .jx-select__wrapper');

                // 3. 聚焦与展开下拉菜单（如果是下拉框形态）
                if (selectWrap) {
                    ['mousedown', 'mouseup', 'click'].forEach(evt => {
                        selectWrap.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                    });
                    await new Promise(r => setTimeout(r, 150));
                }

                input.focus();

                // 4. 原生填入目标值
                let valueSetter;
                if (input.tagName.toLowerCase() === 'textarea') {
                    valueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
                } else {
                    valueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')?.set;
                }
                
                if (valueSetter) {
                    valueSetter.call(input, targetVal);
                } else {
                    input.value = targetVal;
                }
                input.dispatchEvent(new Event('input', { bubbles: true }));
                await new Promise(r => setTimeout(r, 250));

                // 5. 查找并点击匹配的下拉选项（支持模糊/精确匹配）
                let clickedDropdown = false;
                const dropdownItems = Array.from(document.querySelectorAll(
                    '.jx-select-dropdown__item, .el-select-dropdown__item, [role="option"], .jx-select-dropdown li, .el-select-dropdown li, .jx-dropdown-menu__item'
                )).filter(li => {
                    const style = window.getComputedStyle(li);
                    const rect = li.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                });

                const exactMatch = dropdownItems.find(li => li.innerText.trim() === targetVal);
                const partialMatch = dropdownItems.find(li => li.innerText.trim().includes(targetVal));
                const chosen = exactMatch || partialMatch;

                if (chosen) {
                    ['mousedown', 'mouseup', 'click'].forEach(evt => {
                        chosen.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                    });
                    chosen.click();
                    clickedDropdown = true;
                }

                // 6. 如果不是下拉框或者输入的尺寸不在下拉项中：
                // 派发原生回车（Enter）与失焦事件，确保自定义尺寸顺利保存完成
                if (!clickedDropdown) {
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    const enter = { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true, cancelable: true, view: window };
                    input.dispatchEvent(new KeyboardEvent('keydown', enter));
                    input.dispatchEvent(new KeyboardEvent('keypress', enter));
                    input.dispatchEvent(new KeyboardEvent('keyup', enter));
                    input.blur();
                }

                await new Promise(r => setTimeout(r, 200));
                return { success: true, clickedDropdown, filled: targetVal };
            }
            """
            res = self.page.evaluate(js_fill_single, {"groupName": group_name, "targetIdx": idx, "targetVal": val})
            if not res.get("success"):
                self.log(f"⚠️ 填入【{group_name}】第 {idx+1} 项 ({val}) 提示: {res.get('msg')}", "warn")
            time.sleep(0.15)

    # =========================================================================
    # 步骤 3：批量原生上传产品图片 (主图 + 详情图)
    # =========================================================================
    def upload_product_images(self) -> bool:
        """从本地磁盘原生批量上传主图与所有详情图"""
        self._check_cancelled()
        image_files = self.bundle.total_product_images

        if not image_files:
            self.log("没有找到有效的产品图片文件，跳过产品图片上传", "warn")
            return False

        self.log(f"正在执行【步骤 3/4】：准备上传产品图片 (共 {len(image_files)} 张图片: 主图 1 张, 详情图 {len(image_files)-1} 张)...", "info")

        try:
            # 策略 1: 查找已有的多选/单选文件输入框 (排除 SKU 变体区域的 input)
            js_find_input = """
            () => {
                const allInputs = Array.from(document.querySelectorAll('input[type="file"]'));
                const filtered = allInputs.filter(i => {
                    if (i.id === 'sku-file-input' || i.id === 'sku-img-input') return false;
                    if (i.closest('.picture-table-list') || i.closest('.pro-virtual-table__row')) return false;
                    return true;
                });
                return filtered.length > 0;
            }
            """
            has_input = self.page.evaluate(js_find_input)

            if has_input:
                # 定位产品区域的文件 input
                product_inputs = self.page.locator(".product-picture-list input[type='file'], .picture-draggable-list input[type='file'], .pro-field input[type='file'], input[type='file']")
                target_input = None
                for i in product_inputs.all():
                    # 排除 SKU 行的 input
                    is_sku_input = i.evaluate("el => Boolean(el.closest('.picture-table-list') || el.closest('.pro-virtual-table__row'))")
                    if not is_sku_input:
                        target_input = i
                        break

                if target_input:
                    self.log(f"已找到产品图片上传控件，正在原生注入 {len(image_files)} 张本地图片...", "info")
                    target_input.set_input_files(image_files)
                    time.sleep(1.5)
                    self.log(f"✅ 产品图片原生批量上传完成！已传输 {len(image_files)} 张图片", "success")
                    return True

            # 策略 2: 点击添加图片按钮并拦截 File Chooser
            upload_buttons = self.page.locator(".product-picture-list button, .product-picture-list .add-image-box, .product-picture-list .arco-upload, .product-picture-list .upload-icon, .add-image-box, .arco-upload, [class*='upload-btn'], [class*='UploadBtn']")
            target_btn = None
            
            # 过滤掉不可用或属于SKU区域的按钮
            for btn in upload_buttons.all():
                if not btn.is_visible() or not btn.is_enabled():
                    continue
                is_sku_btn = btn.evaluate("el => Boolean(el.closest('.picture-table-list') || el.closest('.pro-virtual-table__row'))")
                if not is_sku_btn:
                    target_btn = btn
                    break

            if target_btn:
                self.log("正在尝试通过点击【添加图片】触发图片库浮层...", "info")
                try:
                    target_btn.click()
                    time.sleep(1.0)
                    
                    has_input = self.page.evaluate(js_find_input)
                    if has_input:
                        product_inputs = self.page.locator(".product-picture-list input[type='file'], .picture-draggable-list input[type='file'], .pro-field input[type='file'], input[type='file']")
                        target_input = None
                        for i in product_inputs.all():
                            is_sku_input = i.evaluate("el => Boolean(el.closest('.picture-table-list') || el.closest('.pro-virtual-table__row'))")
                            if not is_sku_input:
                                target_input = i
                                break
                        
                        if target_input:
                            self.log(f"已在浮层中找到图片上传控件，正在原生注入 {len(image_files)} 张本地图片...", "info")
                            target_input.set_input_files(image_files)
                            time.sleep(1.5)
                            self.log(f"✅ 产品图片(浮层注入)批量上传完成！已传输 {len(image_files)} 张图片", "success")
                            return True
                    else:
                        self.log("弹窗内未找到上传控件", "warn")
                except Exception as ex:
                    self.log(f"点击上传按钮失败: {str(ex)}", "warn")

            self.log("未能定位到产品图片上传区域，请检查页面是否处于商品编辑状态", "warn")
            return False
        except Exception as e:
            self.log(f"上传产品图片异常: {str(e)}", "warn")
            return False

    # =========================================================================
    # 步骤 4：批量原生上传 SKU 变体图片
    # =========================================================================
    def upload_sku_images(self) -> int:
        """为每个 SKU 变体行匹配并上传对应的本地 SKU 图片"""
        self._check_cancelled()
        self.log(f"正在执行【步骤 4/4 前置】：正在为 {len(self.bundle.items)} 个 SKU 匹配并上传变体图片...", "info")

        success_count = 0
        for idx, item in enumerate(self.bundle.items):
            self._check_cancelled()
            if not item.image_full_path or not os.path.exists(item.image_full_path):
                self.log(f"SKU [{item.color}-{item.size}] 图片不存在: {item.image_name}，跳过", "warn")
                continue

            # 查找变体表格或变体列表中对应行
            uploaded = self._upload_single_sku_image(item, idx)
            if uploaded:
                success_count += 1
                self.log(f"[{success_count}/{len(self.bundle.items)}] 成功上传 SKU [{item.color}-{item.size}] 图片: {item.image_name}", "info")
            time.sleep(0.3)

        self.log(f"✅ SKU 变体图片上传完毕，成功上传 {success_count}/{len(self.bundle.items)} 张", "success")
        return success_count

    def _upload_single_sku_image(self, item: SkuItem, row_idx: int) -> bool:
        """为单个 SKU 项匹配变体行并上传图片 (含可能存在的主图与色板图)"""
        try:
            # 获取所有可能的行
            rows = self.page.locator(".picture-table-list .pro-virtual-table__row, .sale-attribute-list tr, .picture-table-list tr").all()
            target_row = None
            
            for r in rows:
                text = r.inner_text()
                if item.color in text and (not item.size or item.size in text):
                    target_row = r
                    break
                    
            if not target_row:
                self.log(f"未能找到匹配 SKU [{item.color}-{item.size}] 的行，跳过", "warn")
                return False

            # 按照 Chrome 插件的逻辑，单独处理各个列的上传框（主图和Swatch图）
            cells = target_row.locator(".pro-virtual-table__row-cell, td").all()
            cells_to_process = []
            
            if len(cells) >= 3:
                cells_to_process = [cells[1], cells[2]]
            elif len(cells) >= 2:
                cells_to_process = [cells[1]]
            else:
                cells_to_process = [target_row]
                
            success = True
            uploaded_any = False
            
            js_find_btn = """
            (cell) => {
                let btns = Array.from(cell.querySelectorAll('.add-image-box, .arco-upload, [class*="upload"]'));
                if (btns.length === 0) {
                    btns = Array.from(cell.querySelectorAll('*')).filter(b => {
                        if (b.tagName === 'INPUT') return false;
                        const cls = (b.className && typeof b.className === 'string') ? b.className.toLowerCase() : '';
                        const txt = (b.textContent || '').trim();
                        return cls.includes('upload') || cls.includes('add') || cls.includes('plus') || txt.includes('添加新图片') || txt.includes('Upload');
                    });
                }
                
                btns = btns.filter(b => {
                    if (b.disabled || b.classList.contains('is-disabled') || b.classList.contains('disabled')) return false;
                    const style = window.getComputedStyle(b);
                    return style.display !== 'none' && style.visibility !== 'hidden' && b.offsetWidth > 0 && b.offsetHeight > 0;
                });
                
                // 保留最深层的元素，避免点击了外层 wrapper
                btns = btns.filter((btn, index, self) => {
                    return !self.some((other, otherIndex) => index !== otherIndex && btn.contains(other));
                });
                
                return btns.length > 0 ? btns[0] : null;
            }
            """
            
            for i, cell in enumerate(cells_to_process):
                self.log(f"正在为 SKU [{item.color}-{item.size}] 扫描第 {i+1} 个图片列...", "info")
                
                # 尝试用 JS 获取精准的上传按钮，兼顾所有潜在的 Class 和文本特征
                btn_handle = cell.evaluate_handle(js_find_btn)
                btn = btn_handle.as_element()
                
                if not btn:
                    self.log(f"第 {i+1} 个图片列未检测到上传按钮，跳过", "info")
                    continue
                    
                self.log(f"发现该列上传按钮，正在触发图片浮层...", "info")
                try:
                    btn.scroll_into_view_if_needed()
                    btn.click()
                    time.sleep(1.0)
                    
                    modal_inputs = self.page.locator("input[type='file']").all()
                    if modal_inputs:
                        modal_inputs[-1].set_input_files(item.image_full_path)
                        time.sleep(1.0)
                        uploaded_any = True
                    else:
                        self.log("SKU弹窗内未找到上传控件", "warn")
                        success = False
                except Exception as ex:
                    self.log(f"点击该列图片按钮失败: {str(ex)}", "warn")
                    success = False

            if not uploaded_any:
                # 尝试直接找行内的 input[type=file]
                inline_inputs = target_row.locator("input[type='file']").all()
                if inline_inputs:
                    for inp in inline_inputs:
                        inp.set_input_files(item.image_full_path)
                        time.sleep(0.5)
                    return True

            return success and uploaded_any

        except Exception as e:
            self.log(f"上传 SKU [{item.color}-{item.size}] 图片异常: {str(e)}", "warn")
        return False

    # =========================================================================
    # 步骤 5：虚拟表格滚动匹配与全自动批量填表
    # =========================================================================
    def fill_virtual_table(self) -> int:
        """智能驱动虚拟表格滚动，逐行匹配 SKU 并精准注入数据"""
        self._check_cancelled()
        self.log(f"正在执行【步骤 4/4】：虚拟表格智能滚动扫描与数据录入 (待填入 {len(self.bundle.items)} 行)...", "info")

        processed_items: Set[SkuItem] = set()
        total_filled = 0
        last_scroll_top = -1.0
        stuck_count = 0
        max_scroll_attempts = 100
        scroll_attempt = 0

        while scroll_attempt < max_scroll_attempts:
            self._check_cancelled()
            scroll_attempt += 1

            # 内部循环：扫描并填充当前可视区域内的所有可用行
            batch_filled_in_step = True
            while batch_filled_in_step:
                self._check_cancelled()
                batch_filled_in_step = False

                # 动态获取当前最新 DOM 渲染的虚拟行
                rows = self.page.locator(".pro-virtual-table__row").all()

                for row in rows:
                    row_text = row.inner_text()

                    # 匹配 SKU
                    matched_items = [
                        it for it in self.bundle.items
                        if it.color in row_text and it.size in row_text and it not in processed_items
                    ]
                    # 按尺寸长度倒序排序，避免 "S" 误匹配 "XXS"
                    matched_items.sort(key=lambda x: len(x.size), reverse=True)

                    if not matched_items:
                        continue

                    match = matched_items[0]

                    # 1. 填入外部产品 ID / 编码
                    self._fill_input_by_placeholder(row, "外部产品 ID", match.code)
                    # 2. 填入商品基本价格
                    self._fill_input_by_placeholder(row, "商品基本价格", match.price)
                    # 3. 填入商品数量 / 库存
                    self._fill_input_by_placeholder(row, "商品数量", match.stock)
                    # 4. 填入平台 SKU
                    self._fill_input_by_placeholder(row, "提供平台SKU", match.platform_sku)
                    # 5. 填入促销价格
                    self._fill_input_by_placeholder(row, "待售产品的价格", match.promo_price)

                    # 6. 填入促销开始与结束日期
                    if match.promo_start and match.promo_end:
                        self._fill_input_by_placeholder(row, "促销开始", match.promo_start)
                        self._fill_input_by_placeholder(row, "促销结束", match.promo_end)

                    # 7. 填入物品状况 (下拉框交互)
                    if match.condition:
                        self._fill_condition_select(row, match.condition)

                    processed_items.add(match)
                    total_filled += 1
                    self.log(f"[{total_filled}/{len(self.bundle.items)}] 成功填入 SKU: [{match.color}-{match.size}] 编码:{match.code} 价格:{match.price} 库存:{match.stock}", "info")

                    # 触发重新抓取 DOM，避免 Vue 重绘导致的旧句柄失效
                    batch_filled_in_step = True
                    time.sleep(0.08)
                    break

            # 检查是否已全部填完
            if len(processed_items) >= len(self.bundle.items):
                self.log(f"🎉 所有 {len(self.bundle.items)} 个 SKU 已全部成功匹配并填入！", "success")
                return total_filled

            # 智能探测并向下滚动虚拟容器
            scroll_result = self._scroll_virtual_table_down()
            if not scroll_result or scroll_result.get("no_scroll", False):
                # 无法滚动，说明表格没有虚拟滚动条或已到最底部
                break

            current_top = scroll_result.get("new_top", 0)
            if abs(current_top - last_scroll_top) <= 2:
                stuck_count += 1
                if stuck_count >= 3:
                    self.log("虚拟表格已滚动到底部", "info")
                    break
            else:
                stuck_count = 0

            last_scroll_top = current_top
            time.sleep(config.SCROLL_WAIT_SEC)

        self.log(f"✅ 虚拟表格扫描结束，共填入 {total_filled} 行数据", "success")
        return total_filled

    def _fill_condition_select(self, row: Locator, condition_text: str):
        """处理行内的物品状况下拉选择框"""
        try:
            selects = row.locator(".jx-select, .el-select").all()
            target_select = None
            for sel in selects:
                t = sel.inner_text()
                # 排除带有 UPC / EAN / ASIN 类型的选择框
                if not any(k in t for k in ["UPC", "EAN", "ASIN", "GTIN"]):
                    target_select = sel
                    break

            if not target_select and selects:
                target_select = selects[-1]

            if target_select:
                target_select.click()
                time.sleep(0.2)

                # 选择匹配的下拉菜单项
                js_select = """
                (cond) => {
                    const items = Array.from(document.querySelectorAll('.jx-select-dropdown__item, .el-select-dropdown__item, .jx-dropdown-menu__item, .el-select-dropdown li, .jx-select-dropdown li'));
                    const visible = items.filter(el => el.getBoundingClientRect().width > 0);
                    const match = visible.find(el => el.textContent.trim() === cond);
                    if (match) {
                        match.click();
                        return true;
                    }
                    return false;
                }
                """
                ok = self.page.evaluate(js_select, condition_text)
                if not ok:
                    target_select.locator("input").press("Enter")
        except Exception:
            pass

    def _scroll_virtual_table_down(self) -> Dict[str, Any]:
        """向下滚动虚拟表格一行/一屏的距离"""
        js_scroll = """
        () => {
            const rows = Array.from(document.querySelectorAll('.pro-virtual-table__row'));
            let container = null;
            if (rows.length > 0) {
                let el = rows[0].parentElement;
                while (el && el !== document.body) {
                    if (el.classList.contains('jx-scrollbar__wrap') || el.classList.contains('pro-virtual-table__body-wrapper')) {
                        container = el;
                        break;
                    }
                    const style = window.getComputedStyle(el);
                    if (style.overflowY === 'auto' || style.overflowY === 'scroll') {
                        container = el;
                        break;
                    }
                    el = el.parentElement;
                }
            }
            if (!container) return { no_scroll: true };

            const prevTop = container.scrollTop;
            const scrollStep = Math.max(container.clientHeight - 80, 200);
            container.scrollTop += scrollStep;
            return {
                no_scroll: false,
                prev_top: prevTop,
                new_top: container.scrollTop,
                scroll_height: container.scrollHeight,
                client_height: container.clientHeight
            };
        }
        """
        try:
            return self.page.evaluate(js_scroll)
        except Exception:
            return {"no_scroll": True}

    # =========================================================================
    # 一键全自动流程
    # =========================================================================
    def run_all(self) -> bool:
        """执行完整全流程：清理 -> 添加变体 -> 上传产品图 -> 上传SKU图 -> 虚拟表格批量填入"""
        start_time = time.time()
        self.log(f"🚀 开始执行全自动录入流程 (共 {len(self.bundle.items)} 个 SKU)...", "info")

        try:
            # 1. 深度清理
            self.clean_existing_data()
            time.sleep(config.STEP_DELAY_SEC)

            # 2. 添加变体
            self.setup_variants()
            time.sleep(config.STEP_DELAY_SEC * 2)

            # 3. 虚拟表格自动填入
            total = self.fill_virtual_table()
            time.sleep(config.STEP_DELAY_SEC)

            # 4. 批量上传产品图片
            self.upload_product_images()
            time.sleep(config.STEP_DELAY_SEC)

            # 5. 上传 SKU 图片
            self.upload_sku_images()
            time.sleep(config.STEP_DELAY_SEC)

            elapsed = round(time.time() - start_time, 1)
            self.log(f"🎉【全流程执行完毕】成功处理 {total} 个 SKU，总耗时 {elapsed} 秒！", "success")
            return True
        except InterruptedError:
            self.log("自动化流程已被用户取消", "warn")
            return False
        except Exception as e:
            self.log(f"❌ 流程执行出错: {str(e)}", "error")
            return False
