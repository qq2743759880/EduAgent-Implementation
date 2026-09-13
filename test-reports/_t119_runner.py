# -*- coding: utf-8 -*-
# 让脚本在 edu-agent 的 venv 上下文能找到 asyncmy
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "edu-agent"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "edu-agent", ".venv", "Lib", "site-packages"))
for p in list(sys.path):
    try:
        import asyncmy
        break
    except Exception:
        pass
# run probe
exec(open(sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "_t119_dbprobe_body.py"), encoding="utf-8").read())