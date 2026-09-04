"""
EduAgent 性能压测脚本（Locust）— Phase 2 性能调优

模拟真实用户学习流程：
  1. 注册/登录 → 获取 Token
  2. 浏览课程列表 → 看课程详情
  3. 进入课次 → 视频打点上报
  4. 做练习题 → 提交作业
  5. AI 问答 → 流式/非流式
  6. 查看仪表盘 → 进度/排行榜

面试考点：
  - 为什么用 Locust？Python 原生、支持 async、分布式、可编程场景
  - 关键指标：RPS（每秒请求数）、P95 延迟、错误率、并发用户数
  - 压测目的：找出系统瓶颈（CPU/内存/数据库/网络），验证限流策略

用法：
  pip install locust
  locust -f tests/performance/locustfile.py --host=http://localhost:8000

  # 无 UI 模式（CI/CD）：
  locust -f tests/performance/locustfile.py --host=http://localhost:8000 \
    --users 100 --spawn-rate 10 --run-time 5m --headless \
    --html=report.html --csv=stats
"""
from __future__ import annotations

import json
import random
import time
import uuid

from locust import HttpUser, SequentialTaskSet, task, between, events
from locust.exception import StopUser


# ============================================================
# 压测配置（可调参数）
# ============================================================
# 每个虚拟用户等待间隔（秒）
USER_WAIT_MIN = 1
USER_WAIT_MAX = 5

# 预置测试账号（需先在数据库创建）
TEST_ACCOUNTS = [
    {"account": "loadtest1", "password": "Test1234!"},
    {"account": "loadtest2", "password": "Test1234!"},
    {"account": "loadtest3", "password": "Test1234!"},
]

# 课程/课次 ID（需根据实际数据库调整）
SAMPLE_SERIES_IDS = [1, 2, 3]
SAMPLE_SESSION_IDS = [1, 2, 3, 4, 5]
SAMPLE_QUESTION_IDS = [1, 2, 3, 4, 5]


# ============================================================
# 请求成功率统计（自定义 Locust 事件）
# ============================================================
@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """压测启动时打印配置信息。"""
    print(f"\n{'='*60}")
    print(f"  EduAgent 性能压测")
    print(f"  目标: {environment.host}")
    print(f"  场景: 完整学习流程（登录→看课→做题→AI问答→仪表盘）")
    print(f"{'='*60}\n")


class EduStudentFlow(SequentialTaskSet):
    """
    模拟学生完整学习流程。

    设计原则：
    - 每个 task 独立，一个失败不影响后续
    - 用 @task 的数字权重控制流量分布（权重越大执行越频繁）
    - 多次登录复用 Token（避免每次都注册）
    """

    def on_start(self):
        """
        用户初始化：注册或登录，获取 Token。
        首次运行用随机账号注册，后续用固定测试账号登录。
        """
        self.token: str | None = None
        self.user_id: int | None = None
        self.session_id: str | None = None  # AI 问答会话 ID
        self.auth_headers: dict = {}

        # 随机选择测试账号
        account = random.choice(TEST_ACCOUNTS)
        self._login(account["account"], account["password"])

    def _login(self, account: str, password: str):
        """登录获取 Token。"""
        with self.client.post(
            "/api/auth/login",
            json={"account": account, "password": password},
            name="POST /api/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                # 契约①：成功响应 {code:0, message, data:{...}}，登录令牌在 data 内
                payload = data.get("data") if isinstance(data, dict) else None
                if not isinstance(payload, dict) or not payload.get("access_token"):
                    resp.failure(f"登录响应壳异常: {str(data)[:200]}")
                    return
                self.token = payload.get("access_token", "")
                self.user_id = payload.get("user", {}).get("user_id", 0)
                self.auth_headers = {"Authorization": f"Bearer {self.token}"}
            elif resp.status_code == 401:
                # 账号不存在，注册一个新账号
                self._register()
            else:
                resp.failure(f"登录失败: {resp.status_code} {resp.text[:200]}")

    def _register(self):
        """注册新账号（压测用）。"""
        suffix = uuid.uuid4().hex[:6]
        with self.client.post(
            "/api/auth/register",
            json={
                "account": f"loadtest_{suffix}",
                "nickname": f"压测用户{suffix}",
                "password": "Test1234!",
                "mobile": f"138{random.randint(10000000, 99999999)}",
            },
            name="POST /api/auth/register",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201):
                # 注册成功（契约①：201 + {code:0,message,data:{user_id}}），不返回 token，需要重新登录
                self._login(f"loadtest_{suffix}", "Test1234!")
            elif resp.status_code == 409:
                # 账号已存在，直接登录
                self._login(f"loadtest_{suffix}", "Test1234!")
            else:
                resp.failure(f"注册失败: {resp.status_code}")

    # ============================================================
    # Task 1: 浏览课程（权重 5，高频操作）
    # ============================================================
    @task(5)
    def browse_courses(self):
        """浏览课程列表 → 查看课程详情。"""
        if not self.token:
            return

        # 1) 课程列表
        with self.client.get(
            "/api/curriculum/series?page=1&page_size=10",
            headers=self.auth_headers,
            name="GET /api/curriculum/series",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"课程列表失败: {resp.status_code}")

        # 2) 随机选一个课程看详情
        series_id = random.choice(SAMPLE_SERIES_IDS)
        with self.client.get(
            f"/api/curriculum/series/{series_id}",
            headers=self.auth_headers,
            name="GET /api/curriculum/series/{id}",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                # 提取课次 ID 供后续任务使用
                data = resp.json()
                modules = data.get("modules", [])
                if modules:
                    sessions = modules[0].get("sessions", [])
                    if sessions:
                        self.session_id = sessions[0].get("id")

    # ============================================================
    # Task 2: 视频打点（权重 3，模拟真实学习行为）
    # ============================================================
    @task(3)
    def video_tick(self):
        """视频播放进度上报（30 秒一次）。"""
        if not self.token or not self.session_id:
            return

        tick_data = {
            "session_id": self.session_id,
            "play_session_id": random.randint(10000, 99999),
            "ticks": [
                {
                    "event_type": "progress",
                    "position_seconds": random.randint(0, 1800),
                    "playback_rate": 1.0,
                    "network_type": "WIFI",
                    "event_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "event_payload": {"action": "play"},
                }
            ],
        }
        with self.client.post(
            "/api/progress/video-ticks",
            json=tick_data,
            headers=self.auth_headers,
            name="POST /api/progress/video-ticks",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 201):
                resp.failure(f"视频打点失败: {resp.status_code}")

    # ============================================================
    # Task 3: 做练习题（权重 3）
    # ============================================================
    @task(3)
    def submit_quiz(self):
        """提交练习题答案。"""
        if not self.token:
            return

        answers = [
            {
                "question_id": random.choice(SAMPLE_QUESTION_IDS),
                "answer": random.choice(["A", "B", "C", "D"]),
            }
            for _ in range(random.randint(1, 3))
        ]
        with self.client.post(
            "/api/interactive/quiz/submit",
            json={"answers": answers},
            headers=self.auth_headers,
            name="POST /api/interactive/quiz/submit",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 201):
                resp.failure(f"提交答案失败: {resp.status_code}")

    # ============================================================
    # Task 4: AI 问答（权重 2，LLM 耗时所以权重低）
    # ============================================================
    @task(2)
    def ai_chat(self):
        """AI 问答（非流式，压测控制超时）。"""
        if not self.token:
            return

        questions = [
            "什么是机器学习？",
            "Python 的装饰器怎么用？",
            "英语现在完成时怎么用？",
        ]
        with self.client.post(
            "/api/chat/answer",
            json={
                "query": random.choice(questions),
                "use_hyde": False,
                "include_history": 2,
                "top_k": 5,
                "model": "fast",
                "timeout": 30,  # 压测时限制超时
            },
            headers=self.auth_headers,
            name="POST /api/chat/answer",
            timeout=35.0,  # Locust 请求超时，比 API 超时多 5 秒
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("degraded_reason"):
                    resp.failure(f"AI 降级: {data['degraded_reason']}")
            elif resp.status_code == 429:
                # 被限流，正常行为
                resp.success()
            else:
                resp.failure(f"AI 问答失败: {resp.status_code}")

    # ============================================================
    # Task 5: 查看仪表盘（权重 4，高频只读操作）
    # ============================================================
    @task(4)
    def view_dashboard(self):
        """查看学习仪表盘。"""
        if not self.token:
            return

        with self.client.get(
            "/api/progress/dashboard?days=7",
            headers=self.auth_headers,
            name="GET /api/progress/dashboard",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"仪表盘失败: {resp.status_code}")

    # ============================================================
    # Task 6: 查看排行榜（权重 2）
    # ============================================================
    @task(2)
    def view_ranking(self):
        """查看积分排行榜。"""
        if not self.token:
            return

        with self.client.get(
            "/api/gamification/ranking?type=points&limit=20",
            headers=self.auth_headers,
            name="GET /api/gamification/ranking",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"排行榜失败: {resp.status_code}")

    # ============================================================
    # Task 7: 健康检查（权重 1，验证基础可用性）
    # ============================================================
    @task(1)
    def health_check(self):
        """健康检查（不依赖认证）。"""
        with self.client.get(
            "/health",
            name="GET /health",
            catch_response=True,
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"健康检查失败: {resp.status_code}")

    def on_stop(self):
        """用户退出时清理。"""
        pass


class EduStudent(HttpUser):
    """
    模拟学生用户。

    配置：
    - wait_time: 每个 task 之间等待 1-5 秒（模拟真实用户行为）
    - tasks: 指向 EduStudentFlow 任务集
    """
    wait_time = between(USER_WAIT_MIN, USER_WAIT_MAX)
    tasks = [EduStudentFlow]

    # 网络超时（Locust 客户端级别）
    network_timeout = 30.0
    connection_timeout = 10.0