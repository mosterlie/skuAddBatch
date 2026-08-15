# 妙手 SKU 批量自动化录入助手 (桌面接管版)

基于 Python + Playwright (CDP 原生接管协议) 开发的独立桌面端 SKU 批量录入工具。彻底废弃旧版浏览器插件与 `server.py` 本地 HTTP 转发架构，实现**零配置、免环境搭建、本地图片原生秒传**。

---

## 🌟 核心特性

1. **原生接管模式 (Takeover Mode)**
   - 点击软件界面的【🚀 启动/打开妙手浏览器】，自动调出配置好的 Chrome / Edge 浏览器。
   - 自动识别并锁定当前打开的“妙手”商品发布/编辑标签页。
   - **持久化登录态**：仅需第一次登录妙手，之后 Cookie/Token 永久保留，下次打开无需重复登录。

2. **本地图片原生直传 (免 `server.py`)**
   - 不再需要运行任何本地 HTTP 服务或处理 Base64 转换。
   - Playwright 原生调用操作系统级别文件注入接口，主图、详情图、SKU 变体图 100% 稳定上传。

3. **全自动智能批量录入**
   - **变体维度生成**：自动添加颜色、尺码等变体维度并清理多余项。
   - **产品图批量上传**：自动上传主图及详情图目录下的所有图片。
   - **SKU 图逐行匹配**：根据数据表配置将对应图片上传到指定 SKU 行。
   - **虚拟表格智能滚动填表**：自动探测虚拟滚动容器，逐行匹配填充外部ID、价格、库存、平台SKU、状况与促销时间。

---

## 📁 目录结构

```
sku_desktop_app/
├── main.py                  # 程序主入口
├── config.py                # 全局配置（CDP 端口、默认路径、超时参数、选择器）
├── requirements.txt         # Python 依赖
├── core/
│   ├── parser.py            # 数据文件解析与本地图片路径校验
│   ├── browser_manager.py   # 浏览器自适应查找、CDP 端口管理与标签页智能识别
│   └── executor.py          # 自动化录入引擎（变体、图片、虚拟表格滚动）
├── gui/
│   └── app_window.py        # 现代化桌面 GUI 界面与实时日志控制台
└── README.md                # 本说明文档
```

---

## 🚀 快速上手

### 1. 运行环境准备
```bash
# 进入桌面程序目录
cd sku_desktop_app

# 安装依赖（仅需 playwright）
python3 -m pip install -r requirements.txt
```

### 2. 启动桌面应用
```bash
python3 main.py
```

### 3. 操作步骤（极简 3 步）：
1. 界面点击 **【🚀 启动/打开妙手浏览器】**（会自动弹出 Chrome 并直达妙手）。
2. 在浏览器中打开你要编辑或发布的商品页面。
3. 在软件中选择 `test_sku.txt` 数据文件，点击 **【▶ 一键全自动批量录入】**。

---

## 📦 打包为独立执行文件 (免 Python 环境分发给其他人)

如果你想把本程序发给团队其他成员使用，可以直接打包成单个免安装程序：

```bash
# 安装 PyInstaller
python3 -m pip install pyinstaller

# 在当前目录下执行打包
pyinstaller --noconsole --onefile main.py -n "MiaoshouSkuAssistant"
```

* **Windows**: 生成 `dist/MiaoshouSkuAssistant.exe`，直接双击运行。
* **macOS**: 生成 `dist/MiaoshouSkuAssistant.app` 或二进制文件。
