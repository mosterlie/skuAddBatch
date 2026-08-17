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
    right: 0; top: 50%; transform: translateY(-50%) translateX(32px);
    width: 52px; height: 58px;
    cursor: grab;
    opacity: 0.2;
    transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
    filter: drop-shadow(-2px 2px 6px rgba(139,92,246,0.3));
  }
  #paw-view:active {
    cursor: grabbing;
  }
  #paw-view:hover, #paw-view.hovered {
    transform: translateY(-50%) translateX(-8px) scale(1.12);
    opacity: 1.0;
    filter: drop-shadow(-5px 4px 12px rgba(139,92,246,0.5));
  }

  /* ═══════ 卡片 ═══════ */
  #card-view {
    position: absolute;
    right: 12px; top: 50%; transform: translateY(-50%);
    width: 232px;
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
  .c3 { background: linear-gradient(135deg, #38bdf8, #0284c7); --sh: rgba(2,132,199,0.4); }
  .c4 { background: linear-gradient(135deg, #4ade80, #16a34a); --sh: rgba(34,197,94,0.4); }
  .c5 { background: linear-gradient(135deg, #60a5fa, #2563eb); --sh: rgba(59,130,246,0.4); }
  .c6 { background: linear-gradient(135deg, #c084fc, #9333ea); --sh: rgba(168,85,247,0.4); }
  .c7 { background: linear-gradient(135deg, #14b8a6, #0d9488); --sh: rgba(20,184,166,0.4); }

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

<div id="paw-view">
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
        <button class="hdr-btn" onclick="doClose()" title="收起面板">✕</button>
      </div>
    </div>
    <div class="btns">
      <button class="ab c1" onclick="sendCmd('1688')"><span class="ic">🔍</span> 1688 货源直达</button>
      <button class="ab c2" onclick="sendCmd('preview')"><span class="ic">📸</span> 1688 素材采集</button>
      <button class="ab c3" onclick="sendCmd('collect')"><span class="ic">📥</span> 打开妙手采集箱</button>
      <button class="ab c4" onclick="sendCmd('calc')"><span class="ic">📊</span> SKU 智能核算</button>
      <button class="ab c5" onclick="sendCmd('miaoshou')"><span class="ic">🔑</span> 妙手免密直达</button>
      <button class="ab c6" onclick="sendCmd('batch')"><span class="ic">📦</span> 一键批量录入</button>
      <button class="ab c7" onclick="sendCmd('open_dir')"><span class="ic">📂</span> 打开操作目录</button>
    </div>
    <button class="fb" onclick="sendCmd('main')">🖥️ 展开完整控制台</button>
  </div>
</div>

<script>
let st='paw', pinned=false, outCnt=0;
let isMouseDown = false;
let hasMoved = false;
let startX = 0, startY = 0;
let lastDragTime = 0;

const paw = document.getElementById('paw-view');

paw.addEventListener('mousedown', (e) => {
  if (e.button !== 0) return;
  isMouseDown = true;
  hasMoved = false;
  startX = e.screenX;
  startY = e.screenY;
  
  try {
    if (window.pywebview && window.pywebview.api) {
      pywebview.api.start_drag(startX, startY);
    }
  } catch(err) {}
});

document.addEventListener('mousemove', (e) => {
  if (!isMouseDown) return;
  
  const dx = e.screenX - startX;
  const dy = e.screenY - startY;
  
  if (!hasMoved && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
    hasMoved = true;
  }
  
  if (hasMoved) {
    const now = performance.now();
    if (now - lastDragTime > 30) {
      lastDragTime = now;
      try {
        if (window.pywebview && window.pywebview.api) {
          pywebview.api.drag(e.screenX, e.screenY);
        }
      } catch(err) {}
    }
  }
});

function resetDragState() {
  if (isMouseDown) {
    isMouseDown = false;
    try {
      if (window.pywebview && window.pywebview.api) {
        pywebview.api.stop_drag();
      }
    } catch(err) {}
  }
}

document.addEventListener('mouseup', (e) => {
  const moved = hasMoved;
  resetDragState();
  if (!moved && st === 'paw') {
    showCard();
  }
});

paw.addEventListener('click', (e) => {
  if (!hasMoved && st === 'paw') {
    showCard();
  }
  hasMoved = false;
});

window.addEventListener('blur', resetDragState);

function callResize(state) {
  try {
    if (window.pywebview && window.pywebview.api) {
      pywebview.api.sz(state);
    }
  } catch(err) {}
}

function sendCmd(action) {
  fetch('http://127.0.0.1:31416/api/dock/cmd?action=' + action)
    .catch(err => console.error(err));
}

function showPaw() {
  st = 'paw';
  isMouseDown = false;
  hasMoved = false;
  const paw = document.getElementById('paw-view');
  paw.classList.remove('hovered');
  paw.classList.remove('hidden');
  document.getElementById('card-view').classList.add('hidden');
  callResize('paw');
}

function showCard() {
  st = 'card';
  isMouseDown = false;
  hasMoved = false;
  const paw = document.getElementById('paw-view');
  paw.classList.remove('hovered');
  paw.classList.add('hidden');
  document.getElementById('card-view').classList.remove('hidden');
  callResize('card');
}

function setHover(hover) {
  if (st === 'paw') {
    const paw = document.getElementById('paw-view');
    if (hover) {
      paw.classList.add('hovered');
    } else {
      paw.classList.remove('hovered');
      isMouseDown = false;
      hasMoved = false;
    }
  }
}

function doClose() { showPaw(); }

document.addEventListener('mouseenter', function() {
  outCnt = 0;
});
document.addEventListener('keydown', function(e) { if (e.key === 'Escape') showPaw(); });

window.addEventListener('pywebviewready', function() { 
  try {
    pywebview.api.ready(); 
  } catch(err) {}
});
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
        self._current_state = 'paw'

    def ready(self):
        pass

    def start_drag(self, sx, sy):
        self._drag_start_sx = sx
        self._drag_start_sy = sy
        win = self._wh.get('win')
        if win:
            self._drag_start_wx = win.x
            self._drag_start_wy = win.y

    def drag(self, sx, sy):
        win = self._wh.get('win')
        if win and hasattr(self, '_drag_start_wx'):
            dx = sx - self._drag_start_sx
            dy = sy - self._drag_start_sy
            new_x = int(self._drag_start_wx + dx)
            new_y = int(self._drag_start_wy + dy)
            try:
                win.move(new_x, new_y)
                self._paw_x = new_x
                self._paw_y = new_y
            except Exception:
                pass

    def stop_drag(self):
        if hasattr(self, '_drag_start_wx'):
            delattr(self, '_drag_start_wx')

    def sz(self, state):
        self._current_state = state
        win = self._wh.get('win')
        if not win:
            return
        
        # Ensure we have initial paw coordinates
        if not hasattr(self, '_paw_x'):
            sw, sh = _get_screen_size()
            self._paw_x = sw - 64
            self._paw_y = sh // 2 - 35

        try:
            if state == 'paw':
                win.resize(64, 70)
                win.move(self._paw_x, self._paw_y)
            else:
                card_x = self._paw_x - 196
                card_y = self._paw_y - 230
                win.resize(260, 535)
                win.move(card_x, card_y)
                try:
                    import AppKit
                    for w in AppKit.NSApp.windows():
                        w.makeKeyAndOrderFront_(None)
                except Exception:
                    pass
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


def _run_dock_process(parent_pid=None):
    """在独立进程/主线程中运行 pywebview 悬浮岛"""
    import webview

    # 启动父进程看门狗守护线程：一旦主程序关闭或被终止，悬浮窗在 0.5s 内感知并同步退出
    if parent_pid is None:
        try:
            ppid = os.getppid()
            if ppid > 1:
                parent_pid = ppid
        except Exception:
            pass

    if parent_pid:
        def _parent_watchdog():
            while True:
                time.sleep(0.5)
                try:
                    os.kill(parent_pid, 0)
                except (ProcessLookupError, OSError):
                    os._exit(0)
                except Exception:
                    pass

        threading.Thread(target=_parent_watchdog, daemon=True, name="ParentWatchdog").start()

    # 针对 macOS Cocoa 底层注入 First Mouse (跨应用首次点击穿透响应)
    try:
        import AppKit, WebKit, objc
        import webview.platforms.cocoa as c

        class NSView(objc.Category(AppKit.NSView)):
            def acceptsFirstMouse_(self, event):
                return True

        class WKWebView(objc.Category(WebKit.WKWebView)):
            def acceptsFirstMouse_(self, event):
                return True

        c.BrowserView.WebKitHost.acceptsFirstMouse_ = lambda self, event: True
    except Exception as e:
        print(f"First mouse swizzle error: {e}", flush=True)

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
        print("Subprocess window shown!", flush=True)
        time.sleep(0.3)
        try:
            import AppKit
            # Transform subprocess to accessory application so it displays and registers clicks/hovers
            AppKit.NSApp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
            
            for w in AppKit.NSApp.windows():
                w.setAcceptsMouseMovedEvents_(True)
                w.setLevel_(AppKit.NSStatusWindowLevel)
                w.setCollectionBehavior_(
                    AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces |
                    AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary |
                    AppKit.NSWindowCollectionBehaviorStationary
                )
                w.setHidesOnDeactivate_(False)
            print("Accessory activation policy set successfully", flush=True)
        except Exception as e:
            print(f"Error in _on_shown: {e}", flush=True)

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

    def _global_mouse_tracker():
        is_hovered = False
        while True:
            time.sleep(0.06)
            try:
                if getattr(api, '_current_state', 'paw') == 'card':
                    continue
                import AppKit
                pt = AppKit.NSEvent.mouseLocation()
                windows = AppKit.NSApp.windows()
                if not windows:
                    continue
                w = windows[0]
                frame = w.frame()
                inside = bool(AppKit.NSPointInRect(pt, frame))
                if inside != is_hovered:
                    is_hovered = inside
                    if inside:
                        win.evaluate_js('setHover(true);')
                    else:
                        win.evaluate_js('setHover(false);')
            except Exception:
                pass

    win.events.shown += _on_shown
    threading.Thread(target=_topmost_keeper, daemon=True).start()
    threading.Thread(target=_global_mouse_tracker, daemon=True, name="GlobalMouseTracker").start()

    webview.start(debug=False)


class FloatingDock:
    """
    高颜值悬浮岛 — 通过子进程运行 pywebview，与 Tkinter 主窗口完美共存
    """

    def __init__(self, master=None, main_app=None, browser_mgr=None):
        self.main_app = main_app
        self.browser_mgr = browser_mgr or (main_app.browser_mgr if main_app else None)
        self._process = None
        import atexit
        atexit.register(self.hide)

    def show(self):
        """启动悬浮岛子进程并传入当前主程序 PID"""
        if self._process and self._process.poll() is None:
            return

        import sys
        current_dir = os.path.dirname(os.path.abspath(__file__))
        dock_script = os.path.join(current_dir, "floating_dock.py")
        parent_pid = str(os.getpid())

        if getattr(sys, 'frozen', False):
            # 运行打包好的可执行文件并传入 --dock
            cmd_args = [sys.executable, "--dock", "--parent-pid", parent_pid]
        else:
            # 源码运行
            cmd_args = [sys.executable, dock_script, "--parent-pid", parent_pid]

        try:
            self._process = subprocess.Popen(
                cmd_args,
                stdout=open('/Users/gx/Desktop/mypro/skuAddBatch/dock_sub.log', 'w'),
                stderr=subprocess.STDOUT
            )
        except Exception as e:
            with open('/Users/gx/Desktop/mypro/skuAddBatch/dock_sub.log', 'a') as f:
                f.write(f"Launch exception: {e}\n")

    def hide(self):
        """完全终止并退出悬浮岛子进程"""
        if self._process and self._process.poll() is None:
            try:
                self._process.terminate()
                self._process.wait(timeout=1.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

    def collapse_immediate(self):
        pass


def launch_standalone_dock():
    """独立模式启动"""
    parent_pid = None
    if "--parent-pid" in sys.argv:
        try:
            idx = sys.argv.index("--parent-pid")
            parent_pid = int(sys.argv[idx + 1])
        except (ValueError, IndexError):
            pass
    _run_dock_process(parent_pid=parent_pid)


if __name__ == "__main__":
    launch_standalone_dock()
