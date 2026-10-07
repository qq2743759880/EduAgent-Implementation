# -*- coding: utf-8 -*-
"""P8 MCP 导入与集成功能 子包入口。

task95 R3 新增模块（延迟加载/认证/重连/动态更新/子代理隔离）：
  - deferred.py       MCP 工具延迟加载（摘要列表常驻，完整描述按需）
  - auth.py           OAuth(Authorization Code+refresh) + API key 注入
  - reconnect.py      自动重连（指数退避 ≤5）
  - dynamic_update.py 动态工具更新监听（不重启会话）
  - isolation.py      子代理级 mcpServers 隔离 + per-tool 结果大小限制
"""
from . import auth, deferred, dynamic_update, isolation, reconnect

__all__ = ["auth", "deferred", "dynamic_update", "isolation", "reconnect"]
