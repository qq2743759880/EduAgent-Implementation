# TO-EXEC-SEED-VIDEO — 视频批量填充方案与实施（用户直接指令）

## 目标

让种子课程视频**真实可播**：82 万行种子数据的 file_url 指向占位域不可达 → 批量生成真实视频文件并批量接线，点击即可播放。

## 可行性（编排者已亲证）

- ffmpeg 9.0.1 在机：`E:\stu\project\AA-video-workflow\.runtime\ffmpeg\ffmpeg-9.0.1-essentials_build\bin\ffmpeg.exe`
- 落盘目录在：`edu-agent/media/videos/`（真实上传历史就在此）
- 服务链路在：后端 `app/main.py:326` 挂载 `/media → _MEDIA_ROOT`，`:9988/media/videos/x.mp4` 直接可取

## 实施步骤

### 1. 生成示例视频库（batch-generate）

- 用 ffmpeg 生成 **120 个**示例 MP4：`testsrc2`/渐变底+课程标题文字（drawtext，中文名从 series 表取），30-60 秒、960×540、H.264+AAC（静音音轨即可）、单文件 ≤3MB，命名 `SEED-<n>.mp4`
- 同步生成 SVG 封面（复用 DATA-SEED-1 的封面生成器风格）120 张到 `edu-agent/media/covers/`
- 产物清单落 `deploy/backups/seed-video-manifest.json`

### 2. DB 批量接线（三核闸铁律）

- **闸①备份**：`session_asset`(file_url/id) 与 `session_video`(cover_url/id) 受影响行逐行 TSV 落 `deploy/backups/seed-video-<date>/`
- **闸②更新**（分批 UPDATE，参数绑定，禁拼接）：
  - `session_asset.file_url` → 按 id 区间轮换指向 `/media/videos/SEED-<n>.mp4`（**全部 61.7 万行都指真实文件**，杜绝任何点击 404；轮换=ID % 120 + 1）
  - `session_video.cover_url` → 轮换指向 `/media/covers/SEED-<n>.svg`
  - 断言：占位域残留=0；本地路径行数==备份行数；表总行数不变
- **闸③幂等**：同脚本重跑改写 0 行
- ⚠️ 禁碰 DATA-SEED-1 已清的 `series.cover_url`/`sys_user.avatar_url`（已是 /assets/seed 本地路径，别覆盖）

### 3. 播放链路验证

- HTTP：抽 10 个 file_url → `curl http://127.0.0.1:9988/media/videos/SEED-*.mp4` 全 200 且 content-type=video/*
- 端到端：CDP 打开 3 门在售课程 learning 页（learning.html?cohort_id=N）→ video 元素 readyState≥3（可播放）截图
- 若前端播放器拼 URL 的 base 指向 3322 而文件在 9988 → 修前端拼 URL 逻辑（本单授权，走 EAPI BASE）

### 4. 交付

- 单 commit：`feat(data)/SEED-VIDEO: 批量生成120真实视频+82万行三核闸接线+播放链路验证`
- 报告 `REPORT-SEED-VIDEO.md`：生成清单/三核闸证据/抽验播放截图/总耗时与磁盘占用（预估 ≤400MB，超限先报告）

## 铁律

禁 push；单 commit；分支对账 feature/opt-waves；三核闸缺一不可；**SQL 全程参数绑定**；ffmpeg 只写 `media/` 目录。
