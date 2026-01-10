#!/usr/bin/env python
"""启动 EvolveRFC 交互式面板"""
import sys
from evolve_rfc.cli.main import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 用户取消，再见！")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        sys.exit(1)
