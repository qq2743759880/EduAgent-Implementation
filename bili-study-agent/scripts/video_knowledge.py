"""Operate the formal EDU Admin API; no compiler or RAG internals are imported.

Run from edu-agent with .venv/Scripts/python.exe scripts/video_knowledge.py --help.
Authentication: EDU_ADMIN_TOKEN, or --account with a hidden password prompt.
Preview saves the reviewed version; approve never fetches a replacement version.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import requests

PREFIX = "/api/admin/video-knowledge/tasks"
TIMEOUT = (5, 30)
STAGES = {"acquiring": "获取视频", "binding": "绑定播放来源", "transcribing": "生成字幕",
          "compiling": "编译学习资料", "review": "等待审核", "publishing": "发布学习资料",
          "ingesting": "知识入库", "complete": "已完成"}
STATUSES = {"queued": "已排队", "running": "执行中", "awaiting_review": "待审核",
            "approved": "已批准", "failed": "失败", "completed": "已完成"}
WORKERS = {"running": "运行中", "paused": "已暂停（需运营恢复生产）", "stopping": "正在完成当前任务后停止",
           "offline": "未运行（排队任务暂不处理）"}


class OperatorError(Exception):
    """Only locally defined safe messages may be displayed."""


def task_id(value: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", value):
        raise argparse.ArgumentTypeError("任务编号须为32位小写十六进制")
    return value


def review_identity(packet: dict, expected_task: str) -> dict:
    if not isinstance(packet, dict) or packet.get("task_id") != expected_task:
        raise OperatorError("审核文件不属于此任务；请使用该任务已审阅的预览文件")
    review = packet.get("review")
    if not isinstance(review, dict):
        raise OperatorError("审核文件格式不正确")
    sha, revision = review.get("artifact_sha256"), review.get("review_revision")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise OperatorError("审核文件缺少完整版本身份；请重新预览并审阅")
    if type(revision) is not int or not 0 <= revision <= 20:
        raise OperatorError("审核文件版本编号不合法")
    return {"artifact_sha256": sha, "review_revision": revision}


class AdminClient:
    def __init__(self, base_url: str):
        parts = urlsplit(base_url)
        if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password
                or parts.query or parts.fragment or parts.path not in ("", "/")):
            raise OperatorError("API地址须为不含凭据或路径的 HTTP/HTTPS 服务地址")
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.trust_env = False
        self.token = ""

    def request(self, method: str, path: str, body=None):
        try:
            response = self.session.request(method, self.base_url + path, json=body, timeout=TIMEOUT)
        except requests.RequestException:
            raise OperatorError("API连接失败或超时；请检查服务地址与运行状态") from None
        errors = {401: "登录失效或未登录；请重新获取运营凭据", 403: "此账号无运营权限，请使用管理员或管理者账号",
                  409: "任务状态或审核版本已更新；请重新预览并审阅后再操作",
                  422: "请求参数不符合正式接口要求", 404: "任务或课次不存在"}
        if not 200 <= response.status_code < 300:
            raise OperatorError(errors.get(response.status_code, "服务暂不可用；请查看任务状态后重试"))
        try:
            packet = response.json()
        except ValueError:
            raise OperatorError("API响应格式不正确；请检查服务地址") from None
        if not isinstance(packet, dict) or str(packet.get("code")) != "0" or "data" not in packet:
            raise OperatorError("API未确认操作成功；请查看任务状态后重试")
        if not isinstance(packet["data"], dict):
            raise OperatorError("API响应数据格式不正确；请检查服务地址")
        return packet["data"]

    def authenticate(self, account: str | None):
        token = "" if account else os.environ.get("EDU_ADMIN_TOKEN", "").strip()
        if not token:
            if not account:
                raise OperatorError("请设置 EDU_ADMIN_TOKEN，或使用 --account 账号并输入密码")
            try:
                password = getpass.getpass("运营账号密码（不回显）：")
            except (EOFError, KeyboardInterrupt):
                raise OperatorError("登录已取消") from None
            data = self.request("POST", "/api/auth/login", {"account": account, "password": password})
            token = data.get("access_token") if isinstance(data, dict) else None
        if not isinstance(token, str) or not token or len(token) > 16384 or "\r" in token or "\n" in token:
            raise OperatorError("登录凭据格式不正确")
        self.token = token
        self.session.headers["Authorization"] = f"Bearer {token}"

    def close(self):
        self.session.close()

    def text(self, value) -> str:
        text = str(value or "")
        if self.token:
            text = text.replace(self.token, "[已隐藏]")
        text = re.sub(r"Bearer\s+\S+", "Bearer [已隐藏]", text, flags=re.IGNORECASE)
        return "".join(c for c in text if c.isprintable())[:512]


def print_task(data: dict, client: AdminClient):
    print(f"任务 {client.text(data.get('id'))} · {STATUSES.get(data.get('status'), '状态未知')} · "
          f"{STAGES.get(data.get('stage'), '阶段未知')}")
    if data.get("error_message"):
        print("原因：" + client.text(data["error_message"]))
    worker = data.get("worker")
    if isinstance(worker, dict):
        print("生产进程：" + WORKERS.get(worker.get("state"), "状态未知"))
    if data.get("playback_available"):
        print("原视频可播放。")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="EduAgent 视频知识运营入口（调用正式 Admin API）")
    result.add_argument("--base-url", default="http://127.0.0.1:9988", help="后端服务地址")
    result.add_argument("--account", help="运营账号；密码使用隐藏输入，默认使用 EDU_ADMIN_TOKEN")
    commands = result.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="为新课次创建视频知识生产任务")
    create.add_argument("--session-id", type=int, required=True)
    create.add_argument("--bvid", required=True)
    create.add_argument("--page", type=int, required=True)
    create.add_argument("--mode", choices=("auto", "asr"), default="auto")
    commands.add_parser("list", help="查看最近任务与生产进程状态")
    for command, help_text in (("status", "查看阶段与失败原因"), ("retry", "重试失败或过期任务")):
        commands.add_parser(command, help=help_text).add_argument("task", type=task_id)
    preview = commands.add_parser("preview", help="保存当前待审内容；此命令不会自动批准")
    preview.add_argument("task", type=task_id)
    preview.add_argument("--output", type=Path, required=True, help="待审 JSON 文件路径")
    reject = commands.add_parser("reject", help="拒绝当前待审内容并按反馈重新编译")
    reject.add_argument("task", type=task_id)
    reject.add_argument("--reason", required=True)
    reject.add_argument("--review", type=Path, required=True, help="已经人工审阅的 preview JSON 文件；拒绝该版本")
    approve = commands.add_parser("approve", help="批准已审阅文件对应的版本；不自动获取新版本")
    approve.add_argument("task", type=task_id)
    approve.add_argument("--review", type=Path, required=True, help="已经人工审阅的 preview JSON 文件")
    return result


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    client = None
    try:
        identity = None
        if args.command == "create" and (args.session_id <= 0 or not 1 <= args.page <= 1000
                or not re.fullmatch(r"BV[0-9A-Za-z]{10}", args.bvid)):
            raise OperatorError("请提供有效课次编号、BVID 与分P编号")
        if args.command == "reject" and not 1 <= len(args.reason.strip()) <= 1000:
            raise OperatorError("审核反馈须为1至1000个非空白字符")
        if args.command in ("approve", "reject"):
            if args.review.stat().st_size > 32 * 1024 * 1024:
                raise OperatorError("审核文件超过大小限制")
            identity = review_identity(json.loads(args.review.read_text(encoding="utf-8")), args.task)
        client = AdminClient(args.base_url)
        client.authenticate(args.account)
        if args.command == "create":
            data = client.request("POST", PREFIX, {"session_id": args.session_id, "bvid": args.bvid,
                "page": args.page, "transcript_mode": args.mode})
        elif args.command == "list":
            data = client.request("GET", PREFIX)
            worker, rows = data.get("worker", {}), data.get("items", [])
            if not isinstance(worker, dict) or not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise OperatorError("API队列响应格式不正确")
            print("生产进程：" + WORKERS.get(worker.get("state"), "状态未知"))
            for row in rows:
                print_task(row, client)
            return 0
        elif args.command == "preview":
            data = client.request("GET", f"{PREFIX}/{args.task}/preview")
            review_identity({"task_id": args.task, "review": data}, args.task)
            # Do not silently overwrite a previously reviewed version.
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump({"task_id": args.task, "review": data}, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            print("预览已保存；请人工审阅笔记、章节、字幕与思维导图。此操作不会自动批准。")
            return 0
        elif args.command == "status":
            data = client.request("GET", f"{PREFIX}/{args.task}")
        else:
            body = identity if args.command == "approve" else ({**identity, "reason": args.reason.strip()} if args.command == "reject" else None)
            data = client.request("POST", f"{PREFIX}/{args.task}/{args.command}", body)
        if not isinstance(data, dict):
            raise OperatorError("API任务响应格式不正确")
        print_task(data, client)
        return 0
    except OperatorError as exc:
        print("操作失败：" + str(exc), file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("操作失败：文件不可读写或格式不正确；请检查审核文件与输出位置", file=sys.stderr)
        return 2
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
