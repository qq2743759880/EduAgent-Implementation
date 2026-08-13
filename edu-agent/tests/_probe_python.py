# -*- coding: utf-8 -*-
"""（临时探针文件，已弃用——仅用于定位可运行后端/打靶的 Python 环境。

定位结论：Z:\\anaconda3\\envs\\kb311（Python 3.11.15）含 fastapi/asyncmy/pytest/
requests/pymysql 全套依赖，为本项目后端 pytest / 打靶脚本的运行环境；
默认 PATH 的 C:\\Python314 缺 fastapi/asyncmy，无法 import app 包。

保留此文件仅为避免 git 工作区残留未说明的探针代码；pytest 不会收集
（文件名不匹配 test_*.py / *_test.py）。后续可安全删除。
"""
