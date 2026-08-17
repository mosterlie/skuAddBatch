"""
妙手 SKU 自动化执行引擎
负责调度变体生成、图片原生批量上传、虚拟表格滚动匹配与字段填入
"""
import os
import re
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
            # 新增：勾选"规格类型"下拉框中的"颜色"和"尺寸"
            self.log("正在检查并勾选【规格类型】中的变体属性...", "info")
            js_select_spec = """
            async (args) => {
                const { hasColor, hasSize } = args;
                
                const formItems = Array.from(document.querySelectorAll('.jx-form-item, .pro-form-item, .sale-attribute-item, .el-form-item'));
                const specGroup = formItems.find(f => {
                    const label = f.querySelector('.jx-form-item__label, label, [class*="label"]');
                    return label && label.innerText.includes('规格类型');
                });
                
                if (!specGroup) return 'not_found';
                
                const selectInput = specGroup.querySelector('.jx-select__input, .el-input__inner, input[type="text"]');
                if (!selectInput) return 'no_input';
                
                let clickedCount = 0;
                
                const searchAndSelect = async (keyword) => {
                    // Focus and click
                    selectInput.focus();
                    ['mousedown', 'mouseup', 'click'].forEach(evt => {
                        selectInput.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                    });
                    await new Promise(r => setTimeout(r, 400));
                    
                    // Set value and trigger input
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
                    nativeInputValueSetter.call(selectInput, keyword);
                    selectInput.dispatchEvent(new Event('input', { bubbles: true }));
                    await new Promise(r => setTimeout(r, 600));
                    
                    // Find dropdown options
                    const popups = Array.from(document.querySelectorAll('.jx-select-dropdown, .el-select-dropdown, .jx-popper')).filter(p => p.style.display !== 'none');
                    for (const popup of popups) {
                        const options = Array.from(popup.querySelectorAll('li'));
                        for (const opt of options) {
                            const txt = opt.innerText.trim();
                            if (txt === keyword || txt.includes(keyword)) {
                                if (!opt.className.includes('is-selected') && !opt.className.includes('selected') && !opt.className.includes('is-checked')) {
                                    opt.scrollIntoView({ block: 'center' });
                                    ['mousedown', 'mouseup', 'click'].forEach(evt => {
                                        opt.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                                    });
                                    clickedCount++;
                                    await new Promise(r => setTimeout(r, 500));
                                    
                                    // 检查是否有弹窗提示“更改规格类型将删除...”并点击“确定”
                                    const confirmBtns = Array.from(document.querySelectorAll('button')).filter(b => b.innerText.includes('确定') || b.innerText.includes('Confirm') || b.innerText.includes('是'));
                                    // 过滤出可见的确定按钮
                                    const visibleConfirmBtns = confirmBtns.filter(b => {
                                        const rect = b.getBoundingClientRect();
                                        return rect.width > 0 && rect.height > 0;
                                    });
                                    
                                    if (visibleConfirmBtns.length > 0) {
                                        const confirmBtn = visibleConfirmBtns[visibleConfirmBtns.length - 1]; // 通常最后一个是最上层弹窗的按钮
                                        ['mousedown', 'mouseup', 'click'].forEach(evt => {
                                            confirmBtn.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                                        });
                                        await new Promise(r => setTimeout(r, 500));
                                    }
                                    
                                    return; // Selected successfully
                                }
                            }
                        }
                    }
                };

                if (hasColor && hasSize) {
                    await searchAndSelect('颜色/尺寸');
                } else if (hasColor) {
                    // 如果下拉框里没有单“颜色”，有可能还是得搜颜色/尺寸，这里按精准匹配
                    await searchAndSelect('颜色');
                } else if (hasSize) {
                    await searchAndSelect('尺寸');
                }
                
                // 收起下拉框
                ['mousedown', 'mouseup', 'click'].forEach(evt => {
                    document.body.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                });
                return clickedCount;
            }
            """
            self.page.evaluate(js_select_spec, {
                "hasColor": len(self.bundle.unique_colors) > 0,
                "hasSize": len(self.bundle.unique_sizes) > 0
            })
            time.sleep(1.0)  # 给页面时间反应，动态生成颜色/尺寸的输入行

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
    # =========================================================================
    # 步骤 4：批量并行上传 SKU 变体图片 (支持虚拟表格自动滚动扫描)
    # =========================================================================
    def _get_picture_table_rows(self) -> List[Locator]:
        """严格在规格图片表格区域内获取当前可见行，绝不混淆下方价格库存表格"""
        selectors = [
            ".picture-table-list .pro-virtual-table__row",
            ".picture-table-list tbody tr",
            ".picture-table-list tr",
            ".sale-attribute-list tbody tr",
            ".sale-attribute-list tr",
            "[class*='picture-table'] tr",
        ]
        for sel in selectors:
            loc = self.page.locator(sel)
            if loc.count() > 0:
                return loc.all()
        return self.page.locator(".picture-table-list tr, .sale-attribute-list tr").all()

    def _scroll_picture_table_down(self) -> bool:
        """向下滚动图片列表容器"""
        js = """
        () => {
            const rows = document.querySelectorAll('.picture-table-list .pro-virtual-table__row, .picture-table-list tbody tr, .picture-table-list tr');
            if (!rows || rows.length === 0) return false;
            
            let el = rows[0];
            let container = null;
            while (el && el !== document.body) {
                const style = window.getComputedStyle(el);
                if ((el.scrollHeight > el.clientHeight + 2) && 
                    (style.overflowY === 'auto' || style.overflowY === 'scroll' || style.overflowY === 'overlay')) {
                    container = el;
                    break;
                }
                el = el.parentElement;
            }
            
            if (!container) return false;
            const prev = container.scrollTop;
            container.scrollTop += 250;
            container.dispatchEvent(new Event('scroll', { bubbles: true }));
            return container.scrollTop > prev;
        }
        """
        try:
            return bool(self.page.evaluate(js))
        except Exception:
            return False

    def upload_sku_images(self) -> int:
        """
        批量并行上传 SKU 变体图片 (支持虚拟表格自动滚动扫描与多屏注入)
        """
        self._check_cancelled()
        total = len(self.bundle.items)
        self.log(f"正在执行【步骤 4/4 前置】：SKU 变体图片批量上传 (共 {total} 个)...", "info")

        injected: Set[SkuItem] = set()

        # 首先将图片表格与页面滚到最顶部
        self._scroll_table_to_top()

        for item in self.bundle.items:
            self._check_cancelled()
            if not item.image_full_path or not os.path.exists(item.image_full_path):
                self.log(f"SKU [{item.color}-{item.size}] 图片不存在: {item.image_name}，跳过", "warn")
                continue

            target_row = self._find_target_row_for_item(item, max_scroll=8)

            if target_row is None:
                self.log(f"未能找到匹配 SKU [{item.color}-{item.size}] 的行，跳过", "warn")
                continue

            try:
                col_gallery, col_swatch = self._classify_image_cells(target_row)
                gallery_files = self._build_sku_gallery_files(item)

                swatch_ok = False
                gallery_ok = False

                # 1. 先上传 Swatch Image 列 (主图第1张)
                if col_swatch is not None and item.image_full_path:
                    swatch_ok = self._inject_files_via_cell_button(col_swatch, [item.image_full_path])
                    time.sleep(0.15)  # 缓冲，等待 Vue 可能的 DOM 重绘

                # 2. 再上传 图库 列 (主图 + 附图)
                if gallery_files:
                    # 重新获取整个行，防止 swatch 上传后 DOM 刷新导致整个 target_row 失效 (Stale Element)
                    target_row = self._find_target_row_for_item(item)
                    if target_row is not None:
                        try:
                            col_gallery, _ = self._classify_image_cells(target_row)
                        except Exception:
                            pass
                        
                        if col_gallery is not None:
                            gallery_ok = self._inject_files_via_cell_button(col_gallery, gallery_files)

                # 如果行内直注失败，尝试弹层兜底
                if (not swatch_ok and item.image_full_path) or (not gallery_ok and gallery_files):
                    # 如果任一必须上传的失败了，调用兜底方法并传入状态
                    modal_swatch, modal_gallery = self._upload_single_sku_image_via_modal(item, target_row, try_swatch=not swatch_ok, try_gallery=not gallery_ok)
                    if modal_swatch: swatch_ok = True
                    if modal_gallery: gallery_ok = True

                # 必须两部分(主图和swatch)应传尽传才算完全成功
                expect_swatch = bool(item.image_full_path)
                expect_gallery = bool(gallery_files)
                
                if (not expect_swatch or swatch_ok) and (not expect_gallery or gallery_ok) and (expect_swatch or expect_gallery):
                    injected.add(item)
                    status_desc = []
                    if swatch_ok:
                        status_desc.append("Swatch(主图第1张)")
                    if gallery_ok:
                        status_desc.append(f"图库({len(gallery_files)}张)")
                    self.log(f"[已上传 {len(injected)}/{total}] SKU [{item.color}-{item.size}] " + " + ".join(status_desc) + f" 已注入: {item.image_name}", "info")
                    time.sleep(0.1)
                else:
                    self.log(f"⚠️ SKU [{item.color}-{item.size}] 图片部分或全部注入失败", "warn")
            except Exception as e:
                self.log(f"SKU [{item.color}-{item.size}] 图片处理异常: {e}", "warn")

        # 统一验证缩略图渲染
        self._wait_sku_images_rendered(len(injected))

        # 完成后将表格滚回顶部，方便下一步骤继续扫描填表
        self._scroll_table_to_top()

        success_count = len(injected)
        self.log(f"✅ SKU 变体图片上传完毕，成功上传 {success_count}/{total} 个", "success")
        return success_count

    def _find_target_row_for_item(self, item: SkuItem, max_scroll: int = 0) -> Optional[Locator]:
        """寻找匹配 SKU (color+size) 的 DOM 行。如果没找到可以自动向下滚动重试。"""
        # 为了防止传入的数据顺序与页面表格顺序不一致，先回到顶部
        self._scroll_table_to_top()
        time.sleep(0.15)
        
        for scroll_attempt in range(max_scroll + 1):
            rows = self._get_picture_table_rows()
            for r in rows:
                try:
                    text = r.inner_text()
                except Exception:
                    continue
                if item.color in text and (not item.size or item.size in text):
                    return r
            if scroll_attempt < max_scroll:
                self._scroll_picture_table_down()
                time.sleep(0.25)
        return None

    def _classify_image_cells(self, row: Locator) -> tuple:
        """
        基于布局特征与列索引识别 SKU 行的两个图片列（参考妙手表格标准 3 列布局）：
        - 列 0：SKU 选项 (颜色/尺寸选择)
        - 列 1：图库列（"图片"列）= SKU 主图(第一位) + 2detail 全部图
        - 列 2：Swatch 列（"Swatch Image"列）= SKU 主图单张 (第1张主图)
        返回 (gallery_col, swatch_col)
        """
        cells = row.locator(".pro-virtual-table__row-cell, td").all()
        
        gallery_col = None
        swatch_col = None

        for idx, cell in enumerate(cells[1:], start=1):  # 跳过首列 SKU 选项
            try:
                text = (cell.inner_text() or "").strip().lower()
                if "添加新图片" in text or "添加" in text:
                    if gallery_col is None:
                        gallery_col = cell
                elif "swatch" in text:
                    if swatch_col is None:
                        swatch_col = cell
            except Exception:
                continue

        if gallery_col is None and len(cells) >= 2:
            gallery_col = cells[1]
        if swatch_col is None and len(cells) >= 3:
            swatch_col = cells[2]

        return gallery_col, swatch_col

    def _build_sku_gallery_files(self, item: SkuItem) -> List[str]:
        """构建图库列上传内容：SKU 主图固定第一位，其后为 2detail 目录全部图片(按文件名自然排序)"""
        files: List[str] = []
        if item.image_full_path and os.path.exists(item.image_full_path):
            files.append(item.image_full_path)
        for p in self._natural_sorted(self.bundle.detail_image_full_paths):
            if os.path.exists(p) and p not in files:
                files.append(p)
        return files

    _JS_FIND_UPLOAD_BTN = """
    (cell) => {
        if (!cell) return null;
        // 1. 优先在单元格内找已知的触发容器或类名
        const selectors = [
            '.upload-trigger-container',
            '.upload-trigger-card',
            '.swatch-image-uploader',
            '.add-image-box',
            '.arco-upload',
            '.jx-upload',
            '[class*="upload"]',
            '[class*="swatch"]',
            '[class*="plus"]'
        ];
        for (const sel of selectors) {
            const el = cell.querySelector(sel);
            if (el) {
                const style = window.getComputedStyle(el);
                if (style.display !== 'none' && style.visibility !== 'hidden') {
                    return el;
                }
            }
        }
        // 2. 查找带加号图标 i/svg 或带 '添加' 文本的元素
        let btns = Array.from(cell.querySelectorAll('i, svg, button, div, span')).filter(b => {
            if (b.tagName === 'INPUT') return false;
            const cls = (b.className && typeof b.className === 'string') ? b.className.toLowerCase() : '';
            const txt = (b.textContent || '').trim();
            return cls.includes('plus') || cls.includes('add') || cls.includes('upload') || cls.includes('icon') || txt.includes('添加新图片') || txt.includes('添加');
        });
        btns = btns.filter(b => {
            const style = window.getComputedStyle(b);
            return style.display !== 'none' && style.visibility !== 'hidden' && b.offsetWidth > 0 && b.offsetHeight > 0;
        });
        if (btns.length > 0) return btns[0];
        
        // 3. 兜底：直接找单元格内的第一个非空 div
        const firstDiv = cell.querySelector('div');
        return firstDiv || cell;
    }
    """

    _JS_FREEZE_SCROLL = """
    () => {
        window.__frozen_els = [];
        const scrollables = document.querySelectorAll('.jx-overlay-dialog, .jx-overlay, .basic-layout-app-main-container, .jx-scrollbar__wrap');
        scrollables.forEach(el => {
            window.__frozen_els.push({el: el, oldOverflow: el.style.getPropertyValue('overflow'), oldOverflowY: el.style.getPropertyValue('overflow-y')});
            el.style.setProperty('overflow', 'hidden', 'important');
            el.style.setProperty('overflow-y', 'hidden', 'important');
        });
    }
    """

    _JS_UNFREEZE_SCROLL = """
    () => {
        if (window.__frozen_els) {
            window.__frozen_els.forEach(item => {
                if (item.oldOverflow) {
                    item.el.style.setProperty('overflow', item.oldOverflow);
                } else {
                    item.el.style.removeProperty('overflow');
                }
                if (item.oldOverflowY) {
                    item.el.style.setProperty('overflow-y', item.oldOverflowY);
                } else {
                    item.el.style.removeProperty('overflow-y');
                }
            });
            window.__frozen_els = null;
        }
    }
    """

    def _inject_files_via_cell_button(self, cell: Locator, files: List[str]) -> bool:
        """
        点击单元格内上传按钮，捕获动态创建的 file input（ElementHandle 固定引用），
        一次性注入文件列表实现多图并发上传（妙手组件原生支持 multiple）。
        """
        if cell is None or not files:
            return False
        valid_files = [f for f in files if os.path.exists(f)]
        if not valid_files:
            return False

        btn = None
        try:
            btn_handle = cell.evaluate_handle(self._JS_FIND_UPLOAD_BTN)
            if btn_handle:
                btn = btn_handle.as_element()
        except Exception:
            pass
        if not btn:
            try:
                btn = cell.as_element()
            except Exception:
                pass
        if not btn:
            return False

        prev_count = len(self.page.query_selector_all("input[type='file']"))
        try:
            self.page.evaluate(self._JS_FREEZE_SCROLL)
            btn.evaluate("el => el.click()")
            time.sleep(0.1) # 稍微等待事件派发
            self.page.evaluate(self._JS_UNFREEZE_SCROLL)
        except Exception:
            try:
                self.page.evaluate(self._JS_UNFREEZE_SCROLL)
            except Exception:
                pass
            return False

        inp = None
        deadline = time.time() + 4.0
        while time.time() < deadline:
            handles = self.page.query_selector_all("input[type='file']")
            if len(handles) > prev_count:
                inp = handles[-1]  # ElementHandle：固定引用，不受后续 DOM 重绘影响
                break
            time.sleep(0.15)

        if inp is None:
            handles = self.page.query_selector_all("input[type='file']")
            if handles:
                inp = handles[-1]

        if inp is None:
            return False

        try:
            if len(valid_files) > 1:
                try:
                    inp.evaluate("el => el.setAttribute('multiple', '')")
                except Exception:
                    pass
                inp.set_input_files(valid_files, timeout=10000)
            else:
                inp.set_input_files(valid_files[0], timeout=5000)
            return True
        except Exception:
            return False

    @staticmethod
    def _input_accepts_multiple(input_el) -> bool:
        """检测 file input 是否支持多文件（含 DOM 属性与 HTML 属性双重判断）"""
        try:
            if input_el.evaluate("el => el.multiple"):
                return True
        except Exception:
            pass
        try:
            return input_el.get_attribute("multiple") is not None
        except Exception:
            return False

    @staticmethod
    def _natural_sorted(paths: List[str]) -> List[str]:
        """文件名自然排序：数字部分按数值比较（detail_2.jpg 排在 detail_10.jpg 前）"""
        def key(p: str):
            name = os.path.basename(p)
            return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]
        return sorted(paths, key=key)

    def _upload_single_sku_image_via_modal(self, item: SkuItem, target_row: Locator, try_swatch: bool = True, try_gallery: bool = True) -> tuple[bool, bool]:
        """兜底路径：点击行内上传按钮捕获动态 input 后注入。
        Swatch 列注入 SKU 主图（第1张）；图库列注入 SKU 主图(第一位) + 2detail 全部图。"""
        swatch_uploaded = False
        gallery_uploaded = False
        try:
            col_gallery, col_swatch = self._classify_image_cells(target_row)
            gallery_files = self._build_sku_gallery_files(item)

            # 1. Swatch 列
            if try_swatch and col_swatch is not None and item.image_full_path:
                if self._inject_files_via_cell_button(col_swatch, [item.image_full_path]):
                    swatch_uploaded = True
                    time.sleep(0.3)
                else:
                    self.log(f"SKU [{item.color}-{item.size}] Swatch 列兜底注入未成功", "warn")

            # 2. 图库列
            if try_gallery and gallery_files:
                target_row = self._find_target_row_for_item(item)
                if target_row is not None:
                    try:
                        col_gallery, _ = self._classify_image_cells(target_row)
                    except Exception:
                        pass
                    if col_gallery is not None:
                        if self._inject_files_via_cell_button(col_gallery, gallery_files):
                            gallery_uploaded = True
                        else:
                            self.log(f"SKU [{item.color}-{item.size}] 图库列兜底注入未成功", "warn")

            return swatch_uploaded, gallery_uploaded
        except Exception as e:
            self.log(f"兜底上传 SKU [{item.color}-{item.size}] 图片异常: {str(e)}", "warn")
            return False, False

    # =========================================================================
    # 测试：第一个 SKU 单行多图同时上传验证
    # =========================================================================
    def test_upload_first_sku_images(self) -> bool:
        """仅测试：对第一个 SKU 对应行，同时测试注入 Swatch Image (主图第1张) 与 图片列 (主图+附图多图)。"""
        self._check_cancelled()
        if not self.bundle.items:
            self.log("⚠️ 无 SKU 数据，请先选择数据文件", "warn")
            return False

        item = self.bundle.items[0]
        self.log(f"🧪【测试模式】仅处理第一个 SKU [{item.color}-{item.size}] 的 Swatch 与图片列", "info")

        gallery_files = self._build_sku_gallery_files(item)
        names = [os.path.basename(f) for f in gallery_files]
        self.log(f"待注入图库 {len(gallery_files)} 张: {', '.join(names)}", "info")

        if not item.image_full_path or not os.path.exists(item.image_full_path):
            self.log(f"⚠️ SKU 主图不存在: {item.image_name}", "warn")
            return False

        # 1. 匹配第一个 SKU 所在行（匹配不到则回退第一行）
        rows = self.page.locator(".picture-table-list .pro-virtual-table__row, .sale-attribute-list tr, .picture-table-list tr").all()
        target_row = None
        for r in rows:
            try:
                text = r.inner_text()
            except Exception:
                continue
            if item.color in text and (not item.size or item.size in text):
                target_row = r
                break
        if target_row is None:
            if rows:
                target_row = rows[0]
                self.log("未精确匹配到 SKU 行，回退使用第一行", "warn")
            else:
                self.log("⚠️ 页面上未找到任何 SKU 行", "warn")
                return False

        # 2. 定位图片列与 Swatch 列
        col_gallery, col_swatch = self._classify_image_cells(target_row)

        swatch_ok = False
        if col_swatch is not None:
            self.log("正在注入 Swatch Image (主图第1张)...", "info")
            swatch_ok = self._inject_files_via_cell_button(col_swatch, [item.image_full_path])
            if swatch_ok:
                self.log(f"✅ Swatch Image 注入成功: {item.image_name}", "info")
                time.sleep(0.3)
            else:
                self.log("⚠️ Swatch Image 注入失败", "warn")

        gallery_ok = False
        target_gallery = col_gallery if col_gallery is not None else target_row
        self.log(f"正在注入图库列 (主图+附图共 {len(gallery_files)} 张)...", "info")
        gallery_ok = self._inject_files_via_cell_button(target_gallery, gallery_files)
        if gallery_ok:
            self.log(f"✅ 图库列多图注入成功 ({len(gallery_files)} 张)", "info")
        else:
            self.log("⚠️ 图库列注入失败", "warn")

        # 3. 校验：观察页面该行缩略图数量
        time.sleep(2.0)
        try:
            thumbs = target_row.evaluate("""r =>
                r.querySelectorAll('img[src^="http"], img[src^="blob:"]').length
            """)
            self.log(f"页面校验：该行当前缩略图数量 = {thumbs}", "info")
        except Exception:
            pass

        if swatch_ok or gallery_ok:
            self.log("🧪 测试注入完成，请观察该行 Swatch 与图片列是否出现缩略图", "success")
            return True
        else:
            self.log("❌ 测试注入未成功，请检查单元格结构与浏览器状态", "error")
            return False

    def _wait_sku_images_rendered(self, expected: int, timeout: float = 20.0):
        """统一轮询等待 SKU 行内缩略图渲染完成（尽力而为，超时不阻塞主流程）"""
        if expected <= 0:
            return
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._check_cancelled()
            try:
                done = self.page.evaluate("""() => {
                    const rows = document.querySelectorAll('.picture-table-list .pro-virtual-table__row, .picture-table-list tr');
                    let count = 0;
                    rows.forEach(r => {
                        if (r.querySelector('img[src^="http"], img[src^="blob:"], [class*="picture"] img, [class*="upload"] img')) count++;
                    });
                    return count;
                }""")
                if done >= expected:
                    self.log(f"✅ 检测到 {done} 行 SKU 图片已渲染完成", "info")
                    return
            except Exception:
                pass
            time.sleep(0.5)
        self.log(f"⚠️ 图片渲染验证超时 ({timeout}s)，部分图片可能仍在上传中，请稍后自行确认", "warn")

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
            
            # 由于可能没有预选项文本，我们可以尝试找所有 select，并排除明显是编码类型的
            possible_selects = []
            for sel in selects:
                t = sel.inner_text().upper()
                if not any(k in t for k in ["UPC", "EAN", "ASIN", "GTIN", "GCID"]):
                    possible_selects.append(sel)
                    
            if possible_selects:
                # 物品状况通常在右侧，或者直接取排除后的第一个
                target_select = possible_selects[-1]
            elif selects:
                target_select = selects[-1]

            if target_select:
                # 使用 evaluate 模拟真实点击，防止 Playwright 原生 click 被拦截
                js_click_select = """(el) => {
                    ['mousedown', 'mouseup', 'click'].forEach(evt => {
                        el.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                    });
                }"""
                target_select.evaluate(js_click_select)
                time.sleep(0.4)

                # 增加一步：如果有 input，就先输入文本过滤一下，这样能确保选项出现
                try:
                    inp = target_select.locator("input")
                    if inp.count() > 0:
                        inp.fill(condition_text)
                        time.sleep(0.4)
                except Exception:
                    pass

                # 选择匹配的下拉菜单项，必须一模一样
                js_select = """
                (cond) => {
                    const items = Array.from(document.querySelectorAll('.jx-select-dropdown__item, .el-select-dropdown__item, .jx-dropdown-menu__item, .el-select-dropdown li, .jx-select-dropdown li'));
                    const visible = items.filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).display !== 'none';
                    });
                    
                    let match = visible.find(el => {
                        // 强制精准匹配
                        return el.innerText.trim() === cond.trim();
                    });
                    
                    if (match) {
                        match.scrollIntoView({ block: 'center' });
                        ['mousedown', 'mouseup', 'click'].forEach(evt => {
                            match.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                        });
                        if (typeof match.click === 'function') match.click();
                        return true;
                    }
                    return false;
                }
                """
                ok = self.page.evaluate(js_select, condition_text)
                
                # 收起下拉框
                self.page.evaluate("""() => {
                    ['mousedown', 'mouseup', 'click'].forEach(evt => {
                        document.body.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                    });
                }""")
                time.sleep(0.2)
                
                # 去掉了兜底的 press("Enter") 逻辑，防止它自动选中包含匹配的不准确选项
                if not ok:
                    self.log(f"未能找到与 '{condition_text}' 完全一致的下拉选项，跳过选择", "warn")
        except Exception as e:
            self.log(f"填充物品状况时发生错误: {e}", "warn")

    def _scroll_virtual_table_down(self) -> Dict[str, Any]:
        """向下滚动价格/库存虚拟表格一行/一屏的距离"""
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
            container.dispatchEvent(new Event('scroll', { bubbles: true }));
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

    def _scroll_table_to_top(self):
        """将页面与所有表格滚动回顶部"""
        js_top = """
        () => {
            const containers = document.querySelectorAll('.jx-scrollbar__wrap, .pro-virtual-table__body-wrapper, .vue-recycle-scroller, .picture-table-list, [class*="picture-table"]');
            containers.forEach(el => {
                el.scrollTop = 0;
                el.dispatchEvent(new Event('scroll', { bubbles: true }));
            });
            window.scrollTo(0, 0);
        }
        """
        try:
            self.page.evaluate(js_top)
            time.sleep(0.3)
        except Exception:
            pass

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
