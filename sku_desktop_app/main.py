#!/usr/bin/env python3
"""
妙手 SKU 批量自动化录入助手 - 主入口
"""
import os
import sys

# 确保项目根目录在 sys.path 中
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from gui.app_window import start_app


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--dock":
        from gui.floating_dock import launch_standalone_dock
        launch_standalone_dock()
        return

    try:
        start_app()
    except KeyboardInterrupt:
        print("\n程序已退出")
    except Exception as e:
        print(f"程序运行异常: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
