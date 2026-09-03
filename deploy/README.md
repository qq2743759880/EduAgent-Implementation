# EduAgent 部署资产（deploy/）

生产部署资产。完整步骤见根目录 `部署上线指南.md`。

## 组成

| 文件 | 作用 |
|------|------|
| `docker-compose.yml` | 一键编排：MySQL + MinIO + etcd + Milvus + MongoDB + Neo4j + 后端 + 前端，含 healthcheck |
| `backend.Dockerfile` | 后端多阶段镜像（deps 缓存 + 非 root appuser + 健康检查） |
| `frontend.Dockerfile` | 前端 Next.js standalone 镜像（非 root nextjs） |
| （根目录）`.dockerignore` | 构建上下文排除（密钥/env/测试不进镜像） |

## 快速开始

```bash
# 1. 生产环境变量
cp edu-agent/.env.production.example .env.production
#    编辑 JWT_SECRET / API_TOKEN / MYSQL_PASSWORD / NEO4J_PASSWORD / LLM_API_KEY 等必填项

# 2. 启动（首次会构建镜像）
docker compose -f deploy/docker-compose.yml --env-file .env.production up -d --build

# 3. 状态
docker compose -f deploy/docker-compose.yml ps

# 4. 验证
curl -s http://localhost:8000/health
curl -s http://localhost:8000/health/detail   # 各存储 ok
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000   # 前端 200
```

## 服务器部署时前端指向后端

`NEXT_PUBLIC_*` 在 build 时内联，需用 build arg 注入：

```bash
NEXT_PUBLIC_API_BASE_URL=http://<服务器IP>:8000 \
  docker compose -f deploy/docker-compose.yml --env-file .env.production up -d --build
```

## 运维

```bash
# 查看日志
docker compose -f deploy/docker-compose.yml logs -f backend

# 重启单个服务
docker compose -f deploy/docker-compose.yml restart backend

# 停止
docker compose -f deploy/docker-compose.yml down

# 停止并删数据卷（慎用，会清库）
docker compose -f deploy/docker-compose.yml down -v
```

## 注意事项

- **生产密钥**：`JWT_SECRET`/`API_TOKEN` 用强随机值，否则后端 fail-fast 拒绝启动（P0-1 安全护栏）。
- **DEBUG**：compose 强制 `DEBUG=false`。
- **数据库迁移**：当前无 Alembic，表由后端 lifespan 启动时创建；首次启动后需导入种子数据（见 `部署上线指南.md` P2 路线图）。
- **MinIO**：`MINIO_ACCESS_KEY/SECRET_KEY` 生产勿用默认 `minioadmin/minioadmin`。

## DEBUG=False 部署前必跑检查单（task123，出包前必跑）

> 目的：关闭鉴权降级后门（`app/auth/dependencies.py` 中 `settings.DEBUG` 触发的虚拟管理员/`X-Force-Role` 后门），确保生产无匿名越权。以下任一不通过即阻断出包。

```bash
# 0) .env / .env.production 核对（config.py Settings）
#    - DEBUG 必须为 false（生产缺省即 false；确认未被显式写成 true）
#    - JWT_SECRET 必须是强随机值（非默认 dev-secret-key-change-in-production）
#      （config.py 582-606 已有 fail-fast：DEBUG=False 且 JWT_SECRET 为公开默认值 → 拒绝启动）

# 1) 无 token 访问 /api/users/me → 必须 401（禁虚拟管理员 / DEBUG_超级管理员）
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/users/me
#    期望：401

# 2) 伪造/垃圾 token → 必须 401
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer garbage.invalid.token" \
  http://localhost:8000/api/users/me
#    期望：401

# 3) X-Force-Role 头无效（DEBUG 后门手势在生产无效）→ 仍 401
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "X-Force-Role: admin" http://localhost:8000/api/users/me
#    期望：401（X-Force-* 后门仅 DEBUG=true 生效）
#    ⚠ 实证登记（task123）：/api/metrics/cache-context-dashboard 已 require_role([ADMIN,MANAGER]) 鉴权；
#      裸 /metrics（Prometheus 抓取端点）当前无 Depends 守护——若 task113 预期该端点也鉴权，需编排者确认
#      并补守卫（见 test-reports/task123-completion-report.md 自检发现）。

# 4) /api/metrics 鉴权生效（依赖 task113）：无 token 返回 401；仅 ADMIN/MANAGER 可读
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/metrics/cache-context-dashboard
#    期望：401
```

### venv 依赖清单（task61 补装，出包前核对）

- **额外生产依赖**：`pdfplumber==0.11.10`（task61 契约⑥ PDF 解析真实成立；图表/PDF 导入链路依赖）。需在后端镜像 `backend.Dockerfile` 的依赖安装段与 `requirements*.txt`（如适用）中同步声明，勿遗漏。
