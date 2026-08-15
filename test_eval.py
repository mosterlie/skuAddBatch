import sys

def test_script():
    js = """
    async (hasColor, hasSize) => {
        const formItems = Array.from(document.querySelectorAll('.jx-form-item, .pro-form-item, .sale-attribute-item, .el-form-item'));
        const specGroup = formItems.find(f => {
            const label = f.querySelector('.jx-form-item__label, label, [class*="label"]');
            return label && label.innerText.includes('规格类型');
        });
        
        if (!specGroup) return 'not_found';
        
        const selectInput = specGroup.querySelector('.jx-select, .el-select, input');
        if (selectInput) {
            ['mousedown', 'mouseup', 'click'].forEach(evt => {
                selectInput.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
            });
            await new Promise(r => setTimeout(r, 800));
            
            const popups = Array.from(document.querySelectorAll('.jx-select-dropdown, .el-select-dropdown, .jx-popper')).filter(p => p.style.display !== 'none');
            let clicked = 0;
            for (const popup of popups) {
                const options = Array.from(popup.querySelectorAll('li'));
                for (const opt of options) {
                    const txt = opt.innerText.trim();
                    const needColor = hasColor && (txt.includes('颜色') || txt.includes('Color'));
                    const needSize = hasSize && (txt.includes('尺寸') || txt.includes('尺码') || txt.includes('Size'));
                    
                    if (needColor || needSize) {
                        if (!opt.className.includes('is-selected') && !opt.className.includes('selected') && !opt.className.includes('is-checked')) {
                            opt.scrollIntoView({ block: 'center' });
                            ['mousedown', 'mouseup', 'click'].forEach(evt => {
                                opt.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
                            });
                            clicked++;
                            await new Promise(r => setTimeout(r, 200));
                        }
                    }
                }
            }
            
            // 收起下拉框
            ['mousedown', 'mouseup', 'click'].forEach(evt => {
                document.body.dispatchEvent(new MouseEvent(evt, { bubbles: true, cancelable: true, view: window }));
            });
            return clicked;
        }
        return 'no_input';
    }
    """
    print(js)

test_script()
