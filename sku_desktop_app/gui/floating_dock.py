"""
桌面边缘吸附快捷唤醒小程序 (pywebview 独立进程版 — 全 HTML/CSS 高颜值)
- 独立子进程运行 pywebview，完美避开 Tkinter 冲突
- 100% 基于 WebKit 渲染，支持圆角、磨砂、渐变、阴影、动画
- 通过向本地 31416 服务发送 HTTP API 请求来触发主应用操作，极其稳定、线程安全
"""
import os
import sys
import time
import threading
import subprocess
from typing import Optional

# ═══════════════════════════════════════════════════════════
# HTML/CSS/JS — 高颜值三级状态悬浮岛
# ═══════════════════════════════════════════════════════════
DOCK_HTML = r'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body {
    width: 100vw; height: 100vh;
    background: transparent;
    font-family: 'Inter', 'SF Pro Display', -apple-system, sans-serif;
    overflow: hidden;
    -webkit-user-select: none; user-select: none;
  }

  /* ═══════ 猫爪 ═══════ */
  #paw-view {
    position: absolute;
    right: 0; top: 50%; transform: translateY(-50%);
    width: 52px; height: 58px;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    filter: drop-shadow(-2px 2px 6px rgba(139,92,246,0.3));
  }
  #paw-view:hover {
    transform: translateY(-50%) translateX(-8px) scale(1.12);
    filter: drop-shadow(-5px 4px 12px rgba(139,92,246,0.5));
  }

  /* ═══════ 水晶球 ═══════ */
  #orb-view {
    position: absolute;
    right: 6px; top: 50%; transform: translateY(-50%);
    width: 58px; height: 58px;
    cursor: pointer;
    display: none;
    animation: orbIn 0.3s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @keyframes orbIn {
    from { opacity: 0; transform: translateY(-50%) translateX(24px) scale(0.6); }
    to   { opacity: 1; transform: translateY(-50%) translateX(0) scale(1); }
  }
  .orb {
    width: 58px; height: 58px;
    border-radius: 50%;
    background: radial-gradient(circle at 32% 32%, #d8b4fe, #a855f7 35%, #7c3aed 65%, #6d28d9);
    box-shadow:
      0 0 24px rgba(139, 92, 246, 0.55),
      0 0 48px rgba(139, 92, 246, 0.2),
      inset 0 -4px 8px rgba(0,0,0,0.12),
      inset 0 4px 8px rgba(255,255,255,0.25);
    display: flex; align-items: center; justify-content: center;
    position: relative;
    transition: all 0.25s ease;
    animation: orbPulse 2.5s ease-in-out infinite;
  }
  @keyframes orbPulse {
    0%, 100% { box-shadow: 0 0 24px rgba(139,92,246,0.55), 0 0 48px rgba(139,92,246,0.2), inset 0 -4px 8px rgba(0,0,0,0.12), inset 0 4px 8px rgba(255,255,255,0.25); }
    50%      { box-shadow: 0 0 32px rgba(139,92,246,0.7), 0 0 64px rgba(139,92,246,0.3), inset 0 -4px 8px rgba(0,0,0,0.12), inset 0 4px 8px rgba(255,255,255,0.25); }
  }
  .orb:hover {
    transform: scale(1.15);
    box-shadow: 0 0 36px rgba(139,92,246,0.8), 0 0 72px rgba(139,92,246,0.35);
  }
  .orb::before {
    content: '';
    position: absolute; top: 7px; left: 12px;
    width: 26px; height: 12px;
    background: rgba(255,255,255,0.3);
    border-radius: 50%;
    transform: rotate(-18deg);
  }
  .orb-face { font-size: 28px; margin-top: 2px; filter: drop-shadow(0 1px 3px rgba(0,0,0,0.2)); }

  /* ═══════ 卡片 ═══════ */
  #card-view {
    position: absolute;
    right: 12px; top: 50%; transform: translateY(-50%);
    width: 232px;
    display: none;
    animation: cardIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  }
  @keyframes cardIn {
    from { opacity: 0; transform: translateY(-50%) translateX(50px) scale(0.88); }
    to   { opacity: 1; transform: translateY(-50%) translateX(0) scale(1); }
  }
  .card {
    background: rgba(255, 255, 255, 0.80);
    backdrop-filter: blur(32px) saturate(200%);
    -webkit-backdrop-filter: blur(32px) saturate(200%);
    border-radius: 24px;
    border: 1px solid rgba(192, 132, 252, 0.28);
    box-shadow:
      0 16px 48px rgba(124, 58, 237, 0.16),
      0 4px 16px rgba(0,0,0,0.05),
      inset 0 1px 0 rgba(255,255,255,0.75);
    padding: 20px 16px 16px;
  }

  .header {
    display: flex; align-items: center;
    margin-bottom: 16px; padding-bottom: 14px;
    border-bottom: 1px solid rgba(148, 103, 255, 0.1);
  }
  .avatar {
    width: 42px; height: 42px;
    background: linear-gradient(135deg, #c084fc 0%, #8b5cf6 50%, #7c3aed 100%);
    border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    font-size: 23px;
    box-shadow: 0 4px 16px rgba(139, 92, 246, 0.35);
    flex-shrink: 0;
  }
  .title-area { flex: 1; margin-left: 10px; }
  .title { font-size: 13px; font-weight: 700; color: #1e1b4b; letter-spacing: -0.03em; }
  .status { display: flex; align-items: center; gap: 5px; margin-top: 3px; }
  .dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 8px rgba(34, 197, 94, 0.5);
    animation: dotPulse 2s ease-in-out infinite;
  }
  .dot.off { background: #ef4444; box-shadow: 0 0 8px rgba(239,68,68,0.5); animation: none; }
  @keyframes dotPulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(0.85)} }
  .status-text { font-size: 10.5px; color: #6b7280; font-weight: 500; }
  .hdr-actions { display: flex; gap: 5px; }
  .hdr-btn {
    width: 28px; height: 28px; border: none; border-radius: 9px;
    background: rgba(241, 245, 249, 0.85);
    cursor: pointer; font-size: 12px;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.2s ease; color: #64748b;
  }
  .hdr-btn:hover { background: rgba(124,58,237,0.12); color: #7c3aed; transform: scale(1.1); }
  .hdr-btn.pinned {
    background: linear-gradient(135deg, #8b5cf6, #7c3aed);
    color: white; box-shadow: 0 3px 10px rgba(124,58,237,0.35);
  }

  .btns { display: flex; flex-direction: column; gap: 8px; }
  .ab {
    display: flex; align-items: center; gap: 10px;
    padding: 11px 14px; border: none; border-radius: 14px;
    cursor: pointer; font-size: 12.5px; font-weight: 600;
    color: white; position: relative; overflow: hidden;
    transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
    letter-spacing: -0.01em;
  }
  .ab::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; bottom: 0;
    background: linear-gradient(180deg, rgba(255,255,255,0.18) 0%, transparent 60%);
    border-radius: 14px; pointer-events: none;
  }
  .ab:hover { transform: translateY(-2px) scale(1.02); box-shadow: 0 6px 22px var(--sh); filter: brightness(1.06); }
  .ab:active { transform: translateY(0) scale(0.97); }
  .ab .ic { font-size: 17px; flex-shrink: 0; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.15)); }

  .c1 { background: linear-gradient(135deg, #fb923c, #ea580c); --sh: rgba(249,115,22,0.4); }
  .c2 { background: linear-gradient(135deg, #fb7185, #e11d48); --sh: rgba(244,63,94,0.4); }
  .c3 { background: linear-gradient(135deg, #4ade80, #16a34a); --sh: rgba(34,197,94,0.4); }
  .c4 { background: linear-gradient(135deg, #60a5fa, #2563eb); --sh: rgba(59,130,246,0.4); }
  .c5 { background: linear-gradient(135deg, #c084fc, #9333ea); --sh: rgba(168,85,247,0.4); }

  .fb {
    display: flex; align-items: center; justify-content: center;
    gap: 6px; width: 100%; padding: 10px; margin-top: 12px;
    border: 1px solid rgba(148, 103, 255, 0.12); border-radius: 14px;
    background: rgba(248, 250, 252, 0.5);
    backdrop-filter: blur(8px);
    cursor: pointer; font-size: 11.5px; font-weight: 600; color: #475569;
    transition: all 0.2s ease;
  }
  .fb:hover { background: rgba(243,232,255,0.6); color: #7c3aed; border-color: rgba(124,58,237,0.25); transform: translateY(-1px); }

  .hidden { display: none !important; }
</style>
</head>
<body>

<div id="paw-view" onclick="showOrb()">
  <svg viewBox="0 0 52 58" xmlns="http://www.w3.org/2000/svg">
    <ellipse cx="28" cy="29" rx="19" ry="24" fill="#fff8f0" stroke="#f0e0d0" stroke-width="0.6"/>
    <ellipse cx="26" cy="30" rx="9" ry="7.5" fill="#fb7185"/>
    <ellipse cx="23" cy="27" rx="3.5" ry="2" fill="rgba(255,190,200,0.5)"/>
    <ellipse cx="17" cy="13" rx="5.5" ry="6" fill="#fb7185"/>
    <ellipse cx="11.5" cy="22" rx="5" ry="5.5" fill="#fb7185"/>
    <ellipse cx="11.5" cy="36" rx="5" ry="5.5" fill="#fb7185"/>
    <ellipse cx="17" cy="45" rx="5.5" ry="6" fill="#fb7185"/>
    <ellipse cx="15" cy="11" rx="2.2" ry="1.5" fill="rgba(255,210,220,0.6)"/>
    <ellipse cx="10" cy="20" rx="2" ry="1.3" fill="rgba(255,210,220,0.6)"/>
    <ellipse cx="10" cy="34" rx="2" ry="1.3" fill="rgba(255,210,220,0.6)"/>
    <ellipse cx="15" cy="43" rx="2.2" ry="1.5" fill="rgba(255,210,220,0.6)"/>
    <rect x="38" y="17" width="14" height="24" rx="6" fill="#faf4ea"/>
  </svg>
</div>

<div id="orb-view" class="hidden" onclick="showCard()">
  <div class="orb"><span class="orb-face">🐱</span></div>
</div>

<div id="card-view" class="hidden">
  <div class="card">
    <div class="header">
      <div class="avatar">🐱</div>
      <div class="title-area">
        <div class="title">Miaoshou Assistant</div>
        <div class="status">
          <div class="dot" id="sDot"></div>
          <span class="status-text" id="sTxt">Connecting...</span>
        </div>
      </div>
      <div class="hdr-actions">
        <button class="hdr-btn" id="bPin" onclick="togglePin()" title="钉住">📌</button>
        <button class="hdr-btn" onclick="doClose()" title="收起">✕</button>
      </div>
    </div>
    <div class="btns">
      <button class="ab c1" onclick="sendCmd('1688')"><span class="ic">🔍</span> 1688 货源直达</button>
      <button class="ab c2" onclick="sendCmd('preview')"><span class="ic">📸</span> 1688 素材采集</button>
      <button class="ab c3" onclick="sendCmd('calc')"><span class="ic">📊</span> SKU 智能核算</button>
      <button class="ab c4" onclick="sendCmd('miaoshou')"><span class="ic">🔑</span> 妙手免密直达</button>
      <button class="ab c5" onclick="sendCmd('batch')"><span class="ic">📦</span> 一键批量录入</button>
    </div>
    <button class="fb" onclick="sendCmd('main')">🖥️ 展开完整控制台</button>
  </div>
</div>

<script>
let st='paw', pinned=false, outCnt=0;

function callResize(state) {
  if (window.pywebview && window.pywebview.api) {
    pywebview.api.sz(state);
  }
}

function sendCmd(action) {
  fetch('http://127.0.0.1:31416/api/dock/cmd?action=' + action)
    .catch(err => console.error(err));
}

function showPaw() {
  st='paw'; outCnt=0;
  document.getElementById('paw-view').classList.remove('hidden');
  document.getElementById('orb-view').classList.add('hidden');
  document.getElementById('card-view').classList.add('hidden');
  callResize('paw');
}
function showOrb() {
  st='orb'; outCnt=0;
  document.getElementById('paw-view').classList.add('hidden');
  document.getElementById('orb-view').classList.remove('hidden');
  document.getElementById('card-view').classList.add('hidden');
  callResize('orb');
}
function showCard() {
  st='card'; outCnt=0;
  document.getElementById('paw-view').classList.add('hidden');
  document.getElementById('orb-view').classList.add('hidden');
  document.getElementById('card-view').classList.remove('hidden');
  callResize('card');
}
function doClose() { showPaw(); }
function togglePin() {
  pinned=!pinned;
  document.getElementById('bPin').classList.toggle('pinned', pinned);
  if (window.pywebview && window.pywebview.api) {
    pywebview.api.set_pin(pinned);
  }
}

document.addEventListener('mouseleave', function() {
  if (st==='orb' || (st==='card' && !pinned)) {
    outCnt++;
    if (outCnt >= 2) { outCnt=0; showPaw(); }
  }
});
document.addEventListener('mouseenter', function() {
  outCnt=0;
  if (st==='paw') showOrb();
});
document.addEventListener('keydown', function(e) { if (e.key==='Escape') showPaw(); });

window.addEventListener('pywebviewready', function() { pywebview.api.ready(); });
</script>
</body>
</html>'''


def _get_screen_size():
    """获取屏幕分辨率"""
    try:
        import AppKit
        frame = AppKit.NSScreen.mainScreen().frame()
        return int(frame.size.width), int(frame.size.height)
    except Exception:
        pass
    return 1920, 1080


# ═══════════════════════════════════════════════════════════
# pywebview API
# ═══════════════════════════════════════════════════════════
class DockAPI:
    def __init__(self, window_holder):
        self._wh = window_holder
        self._pinned = False

    def ready(self):
        pass

    def sz(self, state):
        sw, sh = _get_screen_size()
        win = self._wh.get('win')
        if not win:
            return
        try:
            if state == 'paw':
                win.resize(64, 70)
                win.move(sw - 64, sh // 2 - 35)
            elif state == 'orb':
                win.resize(72, 72)
                win.move(sw - 72, sh // 2 - 36)
            else:
                win.resize(260, 430)
                win.move(sw - 268, sh // 2 - 215)
        except Exception:
            pass

    def set_pin(self, pinned):
        self._pinned = pinned

    def update_status(self, online):
        win = self._wh.get('win')
        if not win:
            return
        try:
            if online:
                win.evaluate_js('document.getElementById("sDot").className="dot";document.getElementById("sTxt").textContent="Online";')
            else:
                win.evaluate_js('document.getElementById("sDot").className="dot off";document.getElementById("sTxt").textContent="Offline";')
        except Exception:
            pass


def _run_dock_process():
    """在独立进程/主线程中运行 pywebview 悬浮岛"""
    import webview

    sw, sh = _get_screen_size()
    wh = {}
    api = DockAPI(wh)

    win = webview.create_window(
        '',
        html=DOCK_HTML,
        width=64, height=70,
        x=sw - 64, y=sh // 2 - 35,
        resizable=False,
        frameless=True,
        transparent=True,
        on_top=True,
        js_api=api,
    )
    wh['win'] = win

    def _on_shown():
        time.sleep(0.3)
        try:
            import AppKit
            for w in AppKit.NSApp.windows():
                w.setLevel_(AppKit.NSStatusWindowLevel)
                w.setCollectionBehavior_(
                    AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
                    AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary |
                    AppKit.NSWindowCollectionBehaviorStationary
                )
                w.setHidesOnDeactivate_(False)
        except Exception:
            pass

    def _topmost_keeper():
        while True:
            time.sleep(3)
            try:
                import AppKit
                for w in AppKit.NSApp.windows():
                    w.setLevel_(AppKit.NSStatusWindowLevel)
                    w.setHidesOnDeactivate_(False)
            except Exception:
                pass

    win.events.shown += _on_shown
    threading.Thread(target=_topmost_keeper, daemon=True).start()

    webview.start(debug=False)


class FloatingDock:
    """
    高颜值悬浮岛 — 通过子进程运行 pywebview，与 Tkinter 主窗口完美共存
    """

    def __init__(self, master=None, main_app=None, browser_mgr=None):
        self.main_app = main_app
        self.browser_mgr = browser_mgr or (main_app.browser_mgr if main_app else None)
        self._process = None

    def show(self):
        """启动悬浮岛子进程"""
        if self._process and self._process.poll() is None:
            return

        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dock_script = os.path.join(current_dir, "floating_dock.py")

        if getattr(sys, 'frozen', False):
            # 运行打包好的可执行文件并传入 --dock
            cmd_args = [sys.executable, "--dock"]
        else:
            # 源码运行
            cmd_args = [sys.executable, dock_script]

        self._process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def hide(self):
        if self._process and self._process.poll() is None:
            self._process.terminate()

    def collapse_immediate(self):
        pass


def launch_standalone_dock():
    """独立模式启动"""
    _run_dock_process()


if __name__ == "__main__":
    launch_standalone_dock()
