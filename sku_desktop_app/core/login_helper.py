"""
妙手自动登录与验证码自动识别处理模块
"""
import os
import sys
import time
import json
from typing import Tuple, Optional, Callable, Dict
from playwright.sync_api import Page, Locator

try:
    import ddddocr
    _ocr_instance = ddddocr.DdddOcr(show_ad=False)
except Exception:
    _ocr_instance = None

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

CREDENTIALS_FILE = os.path.join(config.USER_DATA_DIR, "user_credentials.json")


def load_saved_credentials() -> Dict[str, str]:
    """读取本地已保存的妙手账号密码"""
    if os.path.exists(CREDENTIALS_FILE):
        try:
            with open(CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"account": "", "password": "", "remember": False}


def save_credentials(account: str, password: str, remember: bool = True):
    """保存妙手账号密码到本地持久化存储"""
    os.makedirs(config.USER_DATA_DIR, exist_ok=True)
    data = {"account": account, "password": password, "remember": remember}
    try:
        with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class MiaoshouLoginHelper:
    """负责自动识别妙手登录页面、自动填入账号密码、自动识别 4 位图形验证码并自动提交登录"""

    def __init__(self, page: Page, log_fn: Optional[Callable[[str, str], None]] = None):
        self.page = page
        self.log_fn = log_fn or self._default_log

    def _default_log(self, message: str, level: str = "info"):
        prefix = "ℹ️" if level == "info" else ("✅" if level == "success" else ("⚠️" if level == "warn" else "❌"))
        print(f"[{time.strftime('%H:%M:%S')}] {prefix} {message}")

    def log(self, message: str, level: str = "info"):
        self.log_fn(message, level)

    def is_login_page(self) -> bool:
        """判断当前页面是否为妙手登录页"""
        try:
            url = self.page.url
            # 检查 URL 或页面中的登录表单
            has_login_url = "login" in url or "91miaoshou.com" in url
            has_login_form = self.page.locator(".login-form__input, input[type='password'], .captcha-field__input").count() > 0
            # 并且不是已经在后台了
            is_in_dashboard = self.page.locator(".basic-layout-side, .pro-virtual-table, .sale-attribute-list").count() > 0
            return (has_login_url and has_login_form) and not is_in_dashboard
        except Exception:
            return False

    def auto_solve_captcha_and_login(self, account: str = "", password: str = "", max_retries: int = 4) -> Tuple[bool, str]:
        """
        自动填入账号密码 -> 自动截取图形验证码 -> AI OCR 识别 -> 填入验证码 -> 点击登录
        """
        if not _ocr_instance:
            return False, "OCR 识别库未就绪"

        if not self.is_login_page():
            return True, "当前已处于登录状态，无需重复登录"

        self.log("检测到妙手登录界面，正在启动【AI 自动识别验证码与一键登录】...", "info")

        # 尝试使用本地保存的凭据
        if not account or not password:
            saved = load_saved_credentials()
            if not account:
                account = saved.get("account", "")
            if not password:
                password = saved.get("password", "")

        for attempt in range(1, max_retries + 1):
            try:
                # 1. 检查并填入账号
                acc_inputs = self.page.locator("input[placeholder*='手机号'], input[placeholder*='账号'], input[placeholder*='邮箱'], .login-form__input")
                if acc_inputs.count() > 0:
                    curr_acc = acc_inputs.first.input_value()
                    if not curr_acc and account:
                        acc_inputs.first.click()
                        acc_inputs.first.fill(account)
                        acc_inputs.first.evaluate("""(el, val) => {
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }""", account)
                        self.log(f"已自动填入账号: {account[:3]}****{account[-4:] if len(account)>=7 else ''}", "info")
                    elif not curr_acc and not account:
                        self.log("⚠️ 页面账号输入框为空，请在软件中配置账号或在浏览器中输入一次", "warn")

                # 2. 检查并填入密码
                pwd_inputs = self.page.locator("input[type='password']")
                if pwd_inputs.count() > 0:
                    curr_pwd = pwd_inputs.first.input_value()
                    if not curr_pwd and password:
                        pwd_inputs.first.click()
                        pwd_inputs.first.fill(password)
                        pwd_inputs.first.evaluate("""(el, val) => {
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }""", password)
                        self.log("已自动填入登录密码", "info")
                    elif not curr_pwd and not password:
                        self.log("⚠️ 页面密码输入框为空，请在软件中配置密码或在浏览器中输入一次", "warn")

                # 3. 定位验证码图片元素
                captcha_img = self.page.locator(".captcha-field__img, img.captcha-field__img, img[src*='captcha'], .captcha-field img")
                if captcha_img.count() == 0:
                    self.log("未检测到图形验证码元素，直接点击登录...", "info")
                else:
                    # 截取验证码图片二进制
                    img_bytes = captcha_img.first.screenshot()
                    code_text = _ocr_instance.classification(img_bytes)
                    # 过滤只保留字母和数字
                    clean_code = "".join(ch for ch in code_text if ch.isalnum()).strip()
                    self.log(f"[第 {attempt}/{max_retries} 次] AI 自动识别验证码: 【{clean_code}】", "info")

                    # 填入验证码
                    captcha_input = self.page.locator(".captcha-field__input, input[placeholder*='验证码']")
                    if captcha_input.count() > 0:
                        captcha_input.first.click()
                        captcha_input.first.fill(clean_code)
                        captcha_input.first.evaluate("""(el, val) => {
                            el.focus();
                            el.value = val;
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        }""", clean_code)
                        time.sleep(0.3)

                # 4. 查找并点击登录按钮
                login_btn = self.page.locator("button:has-text('登录'), .login-form__submit-btn, button[class*='submit'], .login-btn")
                if login_btn.count() > 0:
                    login_btn.first.click()
                    self.log("已点击【登录】按钮，正在等待进入系统...", "info")
                    time.sleep(2.5)

                # 5. 检查是否登录成功 (URL 跳转或进入系统主框架)
                if not self.is_login_page():
                    self.log("🎉【登录成功】已自动通过验证码并成功进入妙手后台！", "success")
                    return True, "登录成功"
                else:
                    # 检查是否有错误提示
                    error_el = self.page.locator(".jx-message--error, .el-message--error, .login-form__error, [class*='error']")
                    err_msg = error_el.first.inner_text() if error_el.count() > 0 else ""
                    self.log(f"第 {attempt} 次登录未完成 (页面反馈: {err_msg or '验证码未对齐'})，正在刷新重试...", "warn")
                    if captcha_img.count() > 0:
                        captcha_img.first.click()  # 点击验证码图片刷新
                        time.sleep(1.0)

            except Exception as e:
                self.log(f"自动登录尝试异常: {str(e)}", "warn")
                time.sleep(1.0)

        return False, "自动登录重试超限，请检查账号密码是否填写正确"
