#!/usr/bin/env python
"""启动 EvolveRFC 交互式面板"""
import sys
from evolve_rfc.ui.textual_app import run_textual_app

if __name__ == "__main__":
    try:
        run_textual_app()
    except KeyboardInterrupt:
        print("\n\n👋 用户取消，再见！")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)
