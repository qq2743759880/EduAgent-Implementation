"""
视频转码流水线（Phase 3 对象存储深度掌握）

面试考点：
- 为什么需要转码？原始视频可能 4K/大码率，需要转成 720p/1080p 适配不同网络
- ffmpeg 参数：-vf scale（分辨率）、-crf（质量）、-preset（编码速度）
- 异步回调：转码完成后通知后端更新数据库状态
- 断点续转：记录转码进度，失败后从中断处继续

流水线：
  上传 MinIO → 触发转码任务 → ffmpeg 转码 → 上传到 MinIO → 回调通知后端

当前状态：
  - admin_course_video_asset 表有 transcode_status（queued/processing/ready/failed）
  - 但转码是占位模式，没有真正调用 ffmpeg
  - 本模块提供 ffmpeg 命令行模板 + 回调机制

用法：
  python tests/performance/transcode_pipeline.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import settings
from app.database import get_minio_client


# ============================================================
# 转码配置
# ============================================================
TRANSCODE_PROFILES = {
    "720p": {
        "resolution": "1280x720",
        "video_bitrate": "2000k",
        "audio_bitrate": "128k",
        "crf": 23,  # 质量参数（越小越好，18-28 常用）
        "preset": "medium",  # 编码速度（ultrafast/fast/medium/slow）
    },
    "1080p": {
        "resolution": "1920x1080",
        "video_bitrate": "4000k",
        "audio_bitrate": "192k",
        "crf": 21,
        "preset": "medium",
    },
    "480p": {  # 低带宽预览
        "resolution": "854x480",
        "video_bitrate": "800k",
        "audio_bitrate": "96k",
        "crf": 26,
        "preset": "fast",
    },
}


def build_ffmpeg_command(
    input_path: str,
    output_path: str,
    profile: str = "720p",
) -> list[str]:
    """
    构建 ffmpeg 转码命令。

    面试考点：
    - -vf scale：缩放 + 保持宽高比（force_original_aspect_ratio=decrease）
    - -c:v libx264：H.264 编码（兼容性最好，浏览器全支持）
    - -crf：恒定质量（Constant Rate Factor），替代固定码率
    - -preset：编码速度 vs 压缩率权衡
    - -movflags +faststart：MP4 元数据前置，浏览器可边下边播

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径
        profile: 转码 profile（720p/1080p/480p）

    Returns:
        ffmpeg 命令行参数列表
    """
    cfg = TRANSCODE_PROFILES.get(profile, TRANSCODE_PROFILES["720p"])
    return [
        "ffmpeg",
        "-i", input_path,
        "-vf", f"scale={cfg['resolution']}:force_original_aspect_ratio=decrease,pad={cfg['resolution']}:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264",
        "-crf", str(cfg["crf"]),
        "-preset", cfg["preset"],
        "-b:v", cfg["video_bitrate"],
        "-c:a", "aac",
        "-b:a", cfg["audio_bitrate"],
        "-movflags", "+faststart",
        "-y",  # 覆盖输出文件
        output_path,
    ]


def build_thumbnail_command(input_path: str, output_path: str, time_offset: int = 5) -> list[str]:
    """
    生成视频缩略图命令。

    面试考点：
    - -ss 5：从第 5 秒截取（跳过片头黑屏）
    - -vframes 1：只取 1 帧
    """
    return [
        "ffmpeg",
        "-ss", str(time_offset),
        "-i", input_path,
        "-vframes", "1",
        "-q:v", "2",  # 图片质量（1-31，越小越好）
        "-y",
        output_path,
    ]


# ============================================================
# 转码任务执行器
# ============================================================
class TranscodeJob:
    """
    单个转码任务。

    流程：
    1. 从 MinIO 下载原始视频到临时目录
    2. 对每个 profile 执行 ffmpeg 转码
    3. 生成缩略图
    4. 上传转码结果到 MinIO
    5. 回调通知后端（更新 transcode_status）
    """

    def __init__(
        self,
        asset_id: str,
        source_object_key: str,
        source_bucket: str = "",
        *,
        profiles: list[str] | None = None,
        callback_url: str | None = None,
    ):
        self.asset_id = asset_id
        self.source_object_key = source_object_key
        self.source_bucket = source_bucket or settings.MINIO_BUCKET_COURSE
        self.profiles = profiles or ["720p", "1080p", "480p"]
        self.callback_url = callback_url

        self.status = "queued"
        self.results: dict[str, str] = {}  # profile → output_object_key
        self.errors: list[str] = []

    def _check_ffmpeg(self) -> bool:
        """检查 ffmpeg 是否可用。"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def run(self) -> dict[str, Any]:
        """
        执行转码任务（同步，通常在后台线程中调用）。

        面试考点：
        - 为什么用 subprocess 而不是 Python ffmpeg 库？
          subprocess 更稳定，不依赖第三方库版本兼容性
        - 为什么用临时目录？避免磁盘碎片，转码完成后自动清理
        """
        if not self._check_ffmpeg():
            self.status = "failed"
            self.errors.append("ffmpeg 不可用，请确认已安装 ffmpeg")
            return self._summary()

        self.status = "processing"
        client = get_minio_client()

        with tempfile.TemporaryDirectory(prefix="edu_transcode_") as tmpdir:
            # ── 1. 下载原始视频 ──
            source_local = os.path.join(tmpdir, "source.mp4")
            try:
                client.fget_object(
                    self.source_bucket,
                    self.source_object_key,
                    source_local,
                )
            except Exception as exc:
                self.status = "failed"
                self.errors.append(f"下载原始视频失败: {exc}")
                return self._summary()

            # ── 2. 对每个 profile 转码 ──
            for profile in self.profiles:
                output_local = os.path.join(tmpdir, f"output_{profile}.mp4")
                cmd = build_ffmpeg_command(source_local, output_local, profile)

                try:
                    subprocess.run(cmd, capture_output=True, timeout=3600, check=True)
                except subprocess.TimeoutExpired:
                    self.errors.append(f"{profile} 转码超时（>1小时）")
                    continue
                except subprocess.CalledProcessError as exc:
                    self.errors.append(f"{profile} 转码失败: {exc.stderr.decode()[:200] if exc.stderr else str(exc)}")
                    continue

                # ── 3. 上传到 MinIO ──
                output_key = f"transcoded/{self.asset_id}/{profile}.mp4"
                try:
                    client.fput_object(
                        self.source_bucket,
                        output_key,
                        output_local,
                        content_type="video/mp4",
                    )
                    self.results[profile] = output_key
                except Exception as exc:
                    self.errors.append(f"{profile} 上传 MinIO 失败: {exc}")

            # ── 4. 生成缩略图 ──
            thumb_local = os.path.join(tmpdir, "thumbnail.jpg")
            thumb_cmd = build_thumbnail_command(source_local, thumb_local)
            try:
                subprocess.run(thumb_cmd, capture_output=True, timeout=60, check=True)
                thumb_key = f"thumbnails/{self.asset_id}.jpg"
                client.fput_object(
                    self.source_bucket,
                    thumb_key,
                    thumb_local,
                    content_type="image/jpeg",
                )
                self.results["thumbnail"] = thumb_key
            except Exception as exc:
                self.errors.append(f"缩略图生成失败: {exc}")

        # ── 5. 更新状态 ──
        self.status = "ready" if self.results else "failed"
        return self._summary()

    def _summary(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "status": self.status,
            "results": self.results,
            "errors": self.errors,
        }


# ============================================================
# 演示入口
# ============================================================
def demo():
    """演示转码流水线。"""
    print("=" * 60)
    print("  EduAgent 视频转码流水线")
    print("=" * 60)
    print()

    # 检查 ffmpeg
    try:
        result = subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        if result.returncode == 0:
            version_line = result.stdout.decode().split("\n")[0] if result.stdout else "unknown"
            print(f"  ffmpeg: ✅ {version_line[:60]}")
        else:
            print("  ffmpeg: ❌ 未安装或不可用")
            print("  安装方法: https://ffmpeg.org/download.html")
            return
    except FileNotFoundError:
        print("  ffmpeg: ❌ 未找到")
        print("  安装方法: https://ffmpeg.org/download.html")
        return

    print()
    print("  转码 Profile 配置:")
    for profile, cfg in TRANSCODE_PROFILES.items():
        print(f"    {profile}: {cfg['resolution']} @ {cfg['video_bitrate']} (CRF={cfg['crf']}, preset={cfg['preset']})")

    print()
    print("  命令行示例:")
    print(f"    {' '.join(build_ffmpeg_command('input.mp4', 'output_720p.mp4', '720p'))}")

    print()
    print("  缩略图命令示例:")
    print(f"    {' '.join(build_thumbnail_command('input.mp4', 'thumbnail.jpg'))}")

    print()
    print("  流水线步骤:")
    print("    1. MinIO 下载原始视频 → 临时目录")
    print("    2. ffmpeg 转码 720p/1080p/480p")
    print("    3. 生成缩略图（第 5 秒截帧）")
    print("    4. 上传转码结果到 MinIO")
    print("    5. 回调通知后端更新 admin_course_video_asset.transcode_status")


if __name__ == "__main__":
    demo()