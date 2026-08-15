import sys

def test_script():
    js = """
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
                            await new Promise(r => setTimeout(r, 300));
                            return; // Selected successfully
                        }
                    }
                }
            }
        };

        if (hasColor) {
            await searchAndSelect('颜色');
        }
        if (hasSize) {
            await searchAndSelect('尺寸');
        }
        
        // 收起下拉框
        ['mousedown', 'mouseup', 'click'].forEach(evt => {
            document.body.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
        });
        return clickedCount;
    }
    """
    print(js)

test_script()
