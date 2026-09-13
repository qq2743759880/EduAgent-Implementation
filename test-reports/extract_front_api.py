# -*- coding: utf-8 -*-
import re, os
root = r'E:\stu\project\stu\EduAgent实施手册\edu-frontend\src'
paths = set()
for dirpath, _, files in os.walk(root):
    for f in files:
        if not f.endswith(('.ts', '.tsx')):
            continue
        p = os.path.join(dirpath, f)
        if p.endswith('.test.ts') or p.endswith('.test.tsx'):
            continue
        try:
            src = open(p, encoding='utf-8').read()
        except Exception:
            continue
        # 匹配字符串字面量中的 /api/... 路径
        for m in re.finditer(r'["\'`](/api/[A-Za-z0-9_\-/{}\.]+)["\'`]', src):
            paths.add(m.group(1))
        # 模板拼接如 `/api/admin/users/${id}/role`
        for m in re.finditer(r'["\'`](/api/[A-Za-z0-9_\-/{}\.]*)', src):
            paths.add(m.group(1))
with open(r'E:\stu\project\stu\EduAgent实施手册\test-reports\_frontend_real_api.txt', 'w', encoding='utf-8') as f:
    for p in sorted(paths):
        f.write(p + '\n')
print('count', len(paths))
