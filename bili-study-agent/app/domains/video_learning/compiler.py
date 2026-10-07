"""Native-subtitle compilation using the vendored MIT BiliSum prompt subset.

Two bounded LLM stages compile fresh summary/note; MindMap derives directly
from their validated chapters with exact provenance and no further model call. No BiliSum
service/runtime, database, media acquisition, playback or RAG is imported here.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
import json
import os
import re
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from .artifacts import (
    ArtifactValidationError, ASRCompilerProvenance, ASRRun, Chapter, MindMap, NativeCompilerProvenance, NativeLLMRun,
    StructuredSummary, Transcript, VideoArtifact, _digest, _file, _fingerprint, _json,
    _json_bytes, _no_links, _read, _source_from_discovery, load_video_artifact,
    save_video_artifact, seal_video_artifact,
)
from .vendor.bilisum import prompts

EDU_ROOT = Path(__file__).resolve().parents[3]
# Twenty audited rejections of up to 1000 characters, plus bounded numbering
# and conflict guidance. Never truncate an earlier review requirement.
MAX_REVIEW_FEEDBACK_CHARS = 22000
CODE_FILES = (
    "app/domains/video_learning/compiler.py", "app/domains/video_learning/artifacts.py",
    "app/domains/video_learning/vendor/bilisum/prompts.py",
    "app/domains/video_learning/vendor/bilisum/LICENSE",
    "app/domains/video_learning/vendor/bilisum/provenance.json",
)


@dataclass(frozen=True)
class ModelReply:
    value: dict[str, Any]
    run: NativeLLMRun


class ModelResponseFormatError(ArtifactValidationError):
    """A real, accounted provider reply whose content failed strict JSON parsing.

    The bounded content is private repair/diagnostic input, never exception text.
    Full HTTP-response identity remains in the real run even when truncated here.
    """
    def __init__(self, run: NativeLLMRun, raw_content: str, message: str | None = None):
        super().__init__(message or f"LLM {run.stage} response content is not a strict JSON object")
        self.run = run
        self.raw_content = raw_content[:65536]


@dataclass(frozen=True)
class OpenAIJsonClient:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    timeout: float = 180.0

    @classmethod
    def from_edu(cls) -> OpenAIJsonClient:
        # Read existing config inside the CLI process; do not modify global flags.
        from app.config import settings
        return cls(base_url=settings.LLM_FAST_BASE_URL or settings.LLM_BASE_URL,
                   model=settings.LLM_VIDEO_COMPILER_MODEL or settings.LLM_MODEL_FAST,
                   api_key=settings.LLM_FAST_API_KEY or settings.LLM_API_KEY)

    def complete(self, stage: str, messages: list[dict[str, str]]) -> ModelReply:
        if not self.api_key or not self.model or urlsplit(self.base_url).scheme != "https":
            raise ArtifactValidationError("compiler requires a configured HTTPS LLM endpoint/model/key")
        endpoint = self.base_url.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint += "/chat/completions"
        payload = {"model": self.model, "messages": messages, "temperature": 0,
                   "max_tokens": 16000, "response_format": {"type": "json_object"}, "stream": False}
        # Ark/DeepSeek document this control; bound output to content generation
        # rather than consuming the budget on an unexposed reasoning trace.
        if self.model.startswith(("deepseek-", "doubao-seed-")):
            payload["thinking"] = {"type": "disabled"}
        try:
            with httpx.Client(timeout=httpx.Timeout(self.timeout, connect=15), trust_env=False) as client:
                response = client.post(endpoint, headers={"Authorization": f"Bearer {self.api_key}"}, json=payload)
            if response.status_code != 200:
                raise ArtifactValidationError(f"LLM {stage} request failed with HTTP {response.status_code}")
            body = response.json()
            choice = body["choices"][0]
            usage = body["usage"]
            run = NativeLLMRun.model_validate({"stage": stage, "provider": "openai-compatible", "model": self.model,
                "served_model": body.get("model"),
                "request_sha256": _digest(_json_bytes(payload)), "response_sha256": _digest(response.content),
                "prompt_tokens": usage["prompt_tokens"], "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
                "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens")})
            if choice.get("finish_reason") == "length":
                usage = body.get("usage", {})
                message = choice.get("message", {})
                # Diagnose bounded-output failures without retaining reasoning,
                # provider payloads, headers or credentials in logs/artifacts.
                details = {"finish_reason": "length", "content_chars": len(str(message.get("content") or "")),
                    "reasoning_chars": len(str(message.get("reasoning_content") or "")),
                    "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                    "reasoning_tokens": usage.get("completion_tokens_details", {}).get("reasoning_tokens")}
                raise ModelResponseFormatError(run, str(message.get("content") or ""),
                    f"LLM {stage} output exceeded its bounded token budget: {json.dumps(details)}")
            content = choice["message"]["content"]
            if not isinstance(content, str):
                raise ArtifactValidationError(f"LLM {stage} returned an invalid response contract")
            text = content.strip()
            if text.startswith("```"):
                text = "\n".join(text.splitlines()[1:-1]).strip()
            try:
                value = _json(text.encode("utf-8"))
            except ArtifactValidationError:
                raise ModelResponseFormatError(run, content) from None
            return ModelReply(value, run)
        except httpx.HTTPError as exc:
            # Provider payloads/headers and credentials never enter errors or artifacts.
            raise ArtifactValidationError(f"LLM {stage} transport failed ({type(exc).__name__})") from None
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            if isinstance(exc, ArtifactValidationError):
                raise
            raise ArtifactValidationError(f"LLM {stage} returned an invalid response contract") from None


def _messages(system: str, template: str, **values: str) -> list[dict[str, str]]:
    # BiliSum templates contain LaTeX {1}/{n}; replace named placeholders only.
    # Unescape template JSON examples before inserting source/model content.
    content = template.replace("{{", "{").replace("}}", "}")
    for name, value in values.items():
        content = content.replace("{" + name + "}", value)
    return [{"role": "system", "content": system}, {"role": "user", "content": content}]


def _summary(value: dict[str, Any], transcript: Transcript) -> tuple[dict[str, Any], list[Chapter]]:
    summary = StructuredSummary.model_validate({"title": value["title"], "overview": value["overview"],
                                                "key_points": value["bulletPoints"]})
    anchors = [0.0, *(segment.start for segment in transcript.segments)]
    chapters: list[Chapter] = []
    for raw in value["chapters"]:
        chapter = Chapter.model_validate(raw)
        nearest = min(anchors, key=lambda start: abs(start - chapter.start))
        if abs(nearest - chapter.start) > 2:
            raise ArtifactValidationError("chapter start is not near an actual subtitle segment")
        # A model may anchor the first chapter to the first spoken word rather
        # than the leading silence. Canonical chapters cover the whole video;
        # only an exact first-source anchor within five seconds extends to zero.
        if not chapters and chapter.start == transcript.segments[0].start and chapter.start <= 5:
            nearest = 0.0
        chapters.append(chapter.model_copy(update={"start": nearest}))
    starts = [c.start for c in chapters]
    if not starts or starts[0] != 0 or any(a >= b for a, b in zip(starts, starts[1:])):
        raise ArtifactValidationError("chapters must start at zero and increase")
    return summary.model_dump(mode="json"), chapters


def _note(value: dict[str, Any]) -> str:
    if set(value) != {"knowledgeNoteMarkdown"}:
        raise ArtifactValidationError("knowledge-note stage must return only its Markdown field")
    note = value["knowledgeNoteMarkdown"]
    if not isinstance(note, str) or len(note.strip()) < 200 or not note.lstrip().startswith("# "):
        raise ArtifactValidationError("knowledge note must be a complete nonempty Markdown note")
    fence = None
    for line in note.splitlines():
        if re.fullmatch(r"``[A-Za-z0-9_-]*", line.strip()):
            raise ArtifactValidationError("knowledge note has a malformed code fence")
        match = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if not match:
            continue
        marker, suffix = match.groups()
        if marker != "```":
            raise ArtifactValidationError("knowledge note code fence is unsupported by the student renderer")
        if fence is None:
            fence = (marker[0], len(marker))
        elif marker[0] == fence[0] and len(marker) >= fence[1] and not suffix.strip():
            fence = None
    if fence is not None:
        raise ArtifactValidationError("knowledge note has an unclosed code fence")
    return note


def _mindmap(value: dict[str, Any], chapters: list[Chapter]) -> MindMap:
    data = dict(value)
    data["version"] = 1
    # Upstream templates omit optional parent anchors in their minimal example.
    # Fill structural defaults only; never invent leaf provenance or node content.
    stack = list(data.get("nodes", []))
    while stack:
        node = stack.pop()
        node.setdefault("time_anchor", None)
        node.setdefault("source_chapter_titles", [])
        node.setdefault("source_chapter_starts", [])
        stack.extend(node.get("children", []))
    mindmap = MindMap.model_validate(data)
    refs = {(c.title, c.start) for c in chapters}
    if mindmap.root != mindmap.nodes[0].id or len(mindmap.nodes[0].children) < 3:
        raise ArtifactValidationError("MindMap must have its root and three meaningful branches")
    seen: set[str] = set()
    stack = list(mindmap.nodes)
    while stack:
        node = stack.pop()
        if node.id in seen:
            raise ArtifactValidationError("MindMap node IDs must be unique")
        seen.add(node.id)
        if len(node.source_chapter_titles) != len(node.source_chapter_starts) or any(
            pair not in refs for pair in zip(node.source_chapter_titles, node.source_chapter_starts)
        ):
            raise ArtifactValidationError("MindMap references must copy canonical chapter titles/times")
        if not node.children and (not node.source_chapter_starts or node.time_anchor != min(node.source_chapter_starts)):
            raise ArtifactValidationError("each MindMap leaf needs an exact source chapter anchor")
        stack.extend(node.children)
    return mindmap


def derive_chapter_mindmap(title: str, summary: dict[str, Any], chapters: list[Chapter]) -> ModelReply:
    """Derive a reliable course tree from the existing AI chapter facts.

    Chapter summaries are the only leaf content. Sentence splitting preserves
    their exact text; every descendant points to its own canonical chapter.
    """
    source = {"title": title, "summary": summary, "chapters": [c.model_dump(mode="json") for c in chapters]}
    topics = []
    for index, chapter in enumerate(chapters):
        sentences, current = [], ""
        for char in chapter.summary:
            current += char
            if char in "。！？":
                sentences.append(current.strip())
                current = ""
        if current.strip():
            sentences.append(current.strip())
        leaves = [{"id": f"chapter-{index + 1}-leaf-{number + 1}", "label": text[:24],
            "type": "leaf", "summary": text, "children": [], "time_anchor": chapter.start,
            "source_chapter_titles": [chapter.title], "source_chapter_starts": [chapter.start]}
            for number, text in enumerate(sentences[:3])]
        topics.append({"id": f"chapter-{index + 1}", "label": chapter.title, "type": "topic",
            "summary": chapter.summary, "children": leaves, "time_anchor": chapter.start,
            "source_chapter_titles": [chapter.title], "source_chapter_starts": [chapter.start]})
    mindmap = MindMap.model_validate({"version": 1, "title": title, "root": "root", "nodes": [
        {"id": "root", "label": title, "type": "root", "summary": summary["overview"],
         "children": topics, "time_anchor": None, "source_chapter_titles": [], "source_chapter_starts": []}]})
    value = mindmap.model_dump(mode="json")
    return ModelReply(value, NativeLLMRun(stage="mindmap", provider="deterministic", model="edu-chapter-mindmap-v1",
        request_sha256=_digest(_json_bytes(source)), response_sha256=_digest(_json_bytes(value)),
        prompt_tokens=0, completion_tokens=0, total_tokens=0, reasoning_tokens=0))


def _checkpoint(path: Path, packet: dict[str, Any]) -> None:
    path = _no_links(path)
    packet = {**packet, "record_sha256": _digest(_json_bytes(packet))}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".stage-", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(_json_bytes(packet))
            temp.flush()
            os.fsync(temp.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError:
            raise ArtifactValidationError("concurrent compiler checkpoint already exists; resume after verification") from None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _stage(stage: str, messages: list[dict[str, str]], validate: Callable[[dict[str, Any]], Any],
           client: Any, runs: list[NativeLLMRun], on_stage: Callable[[str], None], cache: Path) -> Any:
    input_sha = _digest(_json_bytes({"model": client.model, "messages": messages}))
    # Stage identity follows its actual source/messages/model, independently of
    # transport code or a later stage's prompt. Successful work survives fixes.
    path = _no_links(cache / input_sha / f"{stage}.json")

    def cached_result(candidate: Path) -> tuple[dict[str, Any], Any, list[NativeLLMRun]]:
        packet = _json(_read(_file(candidate.parent, candidate.name)))
        expected = packet.pop("record_sha256", None)
        if expected != _digest(_json_bytes(packet)) or packet.get("input_sha256") != input_sha:
            raise ArtifactValidationError("compiler checkpoint checksum or stage input changed")
        cached_runs = [NativeLLMRun.model_validate(run) for run in packet["runs"]]
        if not cached_runs or any(run.stage != stage or run.model != client.model for run in cached_runs):
            raise ArtifactValidationError("compiler checkpoint has mismatched model provenance")
        result = validate(packet["value"])
        return packet, result, cached_runs

    if path.exists():
        _, result, cached_runs = cached_result(path)
        runs.extend(cached_runs)
        on_stage(f"{stage}: reused validated checkpoint")
        return result
    # Recover the former cache layout only after the complete original messages
    # (including native transcript/segments), model, checksum and content match.
    # It is a resume seam, never a source for a different subtitle generation.
    old_root = cache
    if old_root.exists():
        candidates: list[Path] = []
        for directory in old_root.iterdir():
            if len(directory.name) != 64 or not directory.is_dir() or directory == cache:
                continue
            # Accept either historical cache layout only after exact message,
            # model and record-hash validation. New writes use one digest level.
            for candidate in (directory / f"{stage}.json", directory / input_sha / f"{stage}.json"):
                candidate = _no_links(candidate)
                if candidate != path and candidate.exists():
                    raw = _json(_read(_file(candidate.parent, candidate.name)))
                    if raw.get("input_sha256") == input_sha:
                        candidates.append(candidate)
        if len(candidates) > 1:
            raise ArtifactValidationError("ambiguous matching legacy compiler checkpoints")
        if candidates:
            packet, result, cached_runs = cached_result(candidates[0])
            _checkpoint(path, packet)
            runs.extend(cached_runs)
            on_stage(f"{stage}: reused verified earlier compiler checkpoint")
            return result
    stage_runs: list[NativeLLMRun] = []
    # At most two calls per stage: one normal request and one bounded contract repair.
    for attempt in range(2):
        on_stage(f"{stage}: request {attempt + 1}/2")
        format_error = None
        try:
            reply = client.complete(stage, messages)
            run = reply.run
        except ModelResponseFormatError as exc:
            format_error = exc
            run = exc.run
        if run.stage != stage or run.model != client.model:
            raise ArtifactValidationError("model reply provenance does not match its compiler stage")
        runs.append(run)
        stage_runs.append(run)
        try:
            if format_error is not None:
                raise format_error
            result = validate(reply.value)
            _checkpoint(path, {"input_sha256": input_sha, "value": reply.value,
                "runs": [run.model_dump(mode="json") for run in stage_runs]})
            on_stage(f"{stage}: validated")
            return result
        except (ArtifactValidationError, ValidationError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, ValidationError):
                errors = exc.errors(include_input=False, include_url=False)
                feedback = json.dumps([{"field": list(e["loc"]), "error": e["msg"]} for e in errors[:8]], ensure_ascii=False)
            else:
                feedback = str(exc)[:1024]
            # Only accounted content-format failures enter repair. HTTP/transport
            # and malformed usage/envelopes escape before this bounded seam.
            failed_content = ({"raw_content": format_error.raw_content} if format_error is not None
                              else {"value": reply.value})
            assistant_content = (format_error.raw_content if format_error is not None
                                 else json.dumps(reply.value, ensure_ascii=False))
            failure_path = cache / ".failures" / run.response_sha256 / f"{stage}-failure.json"
            if not failure_path.exists():
                _checkpoint(failure_path, {"input_sha256": input_sha, "validation_error": feedback,
                    **failed_content, "run": run.model_dump(mode="json")})
            on_stage(f"{stage}: validation failed ({feedback})")
            if attempt:
                raise ArtifactValidationError(f"LLM {stage} failed its content contract after one repair") from None
            messages = [*messages, {"role": "assistant", "content": assistant_content},
                {"role": "user", "content": "上次JSON未通过字段/时间/来源验收，具体错误：" + feedback + "。请重新完整输出JSON，严格遵守原始约束；时间和章节名原样复制提供的数据，不要增加解释。"}]
    raise AssertionError("unreachable bounded stage")


def _code_fingerprints() -> list[dict[str, Any]]:
    return [_fingerprint(name, _read(_file(EDU_ROOT, name))) for name in CODE_FILES]


def compile_video(*, subtitle: Path, discovery: Path, output: Path,
                         client: Any = None, stage_clients: dict[str, Any] | None = None,
                         on_stage: Callable[[str], None] | None = None,
                         review_feedback: str = "") -> Path:
    """Compile fresh derived content from a verified platform-subtitle generation.

    Reuse an immutable pack only when source, discovery, compiler source and model
    identity match. The legacy ASR candidate is never an input to this function.
    """
    on_stage = on_stage or (lambda message: None)
    if not isinstance(review_feedback, str) or len(review_feedback) > MAX_REVIEW_FEEDBACK_CHARS:
        raise ArtifactValidationError("review feedback exceeds its bounded contract")
    subtitle_path = _file(Path(subtitle).parent, Path(subtitle).name)
    discovery_path = _file(Path(discovery).parent, Path(discovery).name)
    subtitle_bytes, discovery_bytes = _read(subtitle_path), _read(discovery_path)
    native = _json(subtitle_bytes)
    origin = native.get("transcript_source")
    if origin not in ("bilibili_subtitle", "asr") or native.get("publication_status") != "source_only_not_compiled":
        raise ArtifactValidationError("input must be an uncompiled verified transcript source")
    asr_run = None
    if origin == "asr":
        try:
            asr_run = ASRRun.model_validate(native["asr_run"])
        except (KeyError, ValidationError) as exc:
            raise ArtifactValidationError("ASR transcript source lacks media provenance") from exc
    try:
        native_source = native["source"]
        source = _source_from_discovery(discovery_bytes, native_source.get("page"))
        if source.platform == "edu":
            if origin != "asr" or asr_run.media_sha256 != source.media_sha256:
                raise ArtifactValidationError("bound video transcript media provenance differs from source discovery")
            expected = source.model_dump(mode="json")
        else:
            expected = {"bvid": source.bvid, "page": source.page, "cid": source.cid,
                        "title": source.title, "source_url": source.url, "duration_seconds": source.duration}
        if any(native_source.get(key) != value for key, value in expected.items()):
            raise ArtifactValidationError("platform subtitle source differs from source discovery")
        transcript = Transcript.model_validate({"full_text": native["transcript"], "segments": native["segments"]})
    except (KeyError, TypeError, ValidationError) as exc:
        raise ArtifactValidationError("native source lacks a valid transcript/source contract") from exc
    previous = 0.0
    for segment in transcript.segments:
        if segment.start < previous or segment.end <= segment.start or segment.end > source.duration:
            raise ArtifactValidationError("native subtitle has invalid time ordering or video bounds")
        previous = segment.end
    if native_source.get("subtitle_segments") != len(transcript.segments):
        raise ArtifactValidationError("native subtitle segment count differs from discovery identity")
    if "".join(transcript.full_text.split()) != "".join("".join(s.text for s in transcript.segments).split()):
        raise ArtifactValidationError("native full transcript differs from its timed segments")
    client = client or OpenAIJsonClient.from_edu()
    if stage_clients and set(stage_clients) - {"summary", "knowledge_note"}:
        raise ArtifactValidationError("unknown compiler model stage override")
    clients = {stage: (stage_clients or {}).get(stage, client)
               for stage in ("summary", "knowledge_note")}
    code_files = _code_fingerprints()
    subtitle_fp = _fingerprint(subtitle_path.name, subtitle_bytes)
    discovery_fp = _fingerprint(discovery_path.name, discovery_bytes)
    output = _no_links(output)
    if output.exists():
        for directory in output.iterdir():
            if len(directory.name) != 64 or not directory.is_dir():
                continue
            artifact_file = directory / "artifact.json"
            if not artifact_file.exists():
                continue
            existing = load_video_artifact(artifact_file)
            c = existing.compiler
            same_origin = isinstance(c, NativeCompilerProvenance) and c.transcript_origin == ("asr" if asr_run else "platform_subtitle")
            same_stages = same_origin and all(
                (run.provider == "deterministic" and run.model == "edu-chapter-mindmap-v1")
                if run.stage == "mindmap" else run.model == clients[run.stage].model for run in c.llm_runs)
            if not review_feedback and same_stages and c.subtitle.model_dump() == subtitle_fp and c.discovery.model_dump() == discovery_fp and [f.model_dump() for f in c.code_files] == code_files:
                on_stage("reusing verified native immutable artifact")
                return artifact_file
    segments_json = json.dumps([s.model_dump() for s in transcript.segments], ensure_ascii=False, separators=(",", ":"))
    # Stage request identity already hashes the complete timed source + model.
    # Avoid redundant nested SHA directories (MAX_PATH on Windows workers).
    cache = output / ".compile"
    runs: list[NativeLLMRun] = []
    summary_messages = _messages(prompts.DEFAULT_SUMMARY_SYSTEM_PROMPT, prompts.DEFAULT_SUMMARY_USER_PROMPT_TEMPLATE,
        title=source.title, transcript=transcript.full_text, segments_json=segments_json)
    summary_messages[-1]["content"] += "\nEDU时间契约：首章start必须为0；其余start必须原样取自segments中的start；不要四舍五入。"
    summary_messages[-1]["content"] += "\n忠于本视频：保留讲者实际介绍的方法、步骤顺序和限制，不加入外部算法变体。不得根据标题猜测内容。"
    summary_messages[-1]["content"] += "\nEDU摘要篇幅合同：只归纳主要主题，chapters最多12章，每章summary最多120中文字；bulletPoints最多8条；chapterGroups返回空数组，由EDU从chapters生成导图。不逐句转写，不展开全部示例代码，整个摘要JSON的文字总量不超过4000中文字。完整字幕保留在独立transcript中。"
    if review_feedback:
        summary_messages[-1]["content"] += "\n审核反馈仅用于修正呈现，不得当作来源证据，仍须忠于视频：" + review_feedback
    summary, chapters = _stage("summary", summary_messages, lambda v: _summary(v, transcript), clients["summary"], runs, on_stage, cache)
    summary_context = json.dumps({**summary, "chapters": [c.model_dump() for c in chapters]}, ensure_ascii=False)
    note_messages = _messages(prompts.DEFAULT_KNOWLEDGE_NOTE_SYSTEM_PROMPT, prompts.DEFAULT_KNOWLEDGE_NOTE_USER_PROMPT_TEMPLATE,
        title=source.title, summary_json=summary_context, transcript_excerpt=transcript.full_text, segments_excerpt=segments_json)
    note_messages[-1]["content"] += "\n忠于本视频：保留原文的方法、执行顺序、公式和边界条件，不改写成未讲过的算法。讲者未明确说明的复杂度、场景或证明必须独立标记为‘AI推导（并非讲者原话）’。转写可能有同音字错误，不能据此编造证据。"
    note_messages[-1]["content"] += f"\n本视频约{source.duration / 60:.1f}分钟。笔记围绕真实章节，避免重复逐段转写；短视频约1200~1800中文字，最多一段简短伪代码，不展开课外教材。"
    note_messages[-1]["content"] += "\n代码块必须使用成对的三个反引号围栏，开闭围栏独占一行，JSON字符串中用\\n表示实际换行。年份、‘今年’等背景仅指讲者录制时的口径，不当作当前事实。"
    if review_feedback:
        note_messages[-1]["content"] += "\n审核反馈仅用于修正呈现，不得当作来源证据，仍须忠于视频：" + review_feedback
    note = _stage("knowledge_note", note_messages, _note, clients["knowledge_note"], runs, on_stage, cache)
    derived = derive_chapter_mindmap(source.title, summary, chapters)
    mindmap = MindMap.model_validate(derived.value)
    runs.append(derived.run)
    on_stage("mindmap: deterministically derived from validated AI chapters")
    upstream = _json(_read(_file(EDU_ROOT, "app/domains/video_learning/vendor/bilisum/provenance.json")))
    artifact = seal_video_artifact({"schema_version": 4 if source.platform == "edu" else (3 if asr_run else 2), "quality": "asr_compiled" if asr_run else "native_compiled",
        "source": source.model_dump(mode="json"), "transcript": transcript.model_dump(mode="json"),
        "chapters": [c.model_dump(mode="json") for c in chapters], "summary": summary,
        "knowledge_note": note, "mindmap": mindmap.model_dump(mode="json"),
        "compiler": {"name": "EduVideoCompiler", "version": "2" if asr_run else "1", "transcript_origin": "asr" if asr_run else "platform_subtitle",
            **({"asr_run": asr_run.model_dump(mode="json")} if asr_run else {}),
            "subtitle": subtitle_fp, "discovery": discovery_fp, "code_files": code_files,
            "upstream_repo": upstream["repo"], "upstream_head": upstream["head"], "upstream_license": upstream["license"],
            "upstream_source_files": upstream["source_files"], "llm_runs": [run.model_dump(mode="json") for run in runs]}})
    result = save_video_artifact(artifact, output)
    on_stage("native artifact sealed and persisted")
    return result


def compile_native_video(**kwargs: Any) -> Path:
    """Backwards-compatible native-only entry; existing callers keep their contract."""
    source = _json(_read(_file(Path(kwargs["subtitle"]).parent, Path(kwargs["subtitle"]).name)))
    if source.get("transcript_source") != "bilibili_subtitle":
        raise ArtifactValidationError("input must be an uncompiled platform-subtitle source")
    return compile_video(**kwargs)


def verify_native_inputs(artifact: VideoArtifact, *, subtitle: Path, discovery: Path) -> None:
    """Audit native input and current compiler fingerprints independently of LLMs."""
    if not isinstance(artifact.compiler, NativeCompilerProvenance):
        raise ArtifactValidationError("artifact is not a native compiler generation")
    for path, fingerprint in ((subtitle, artifact.compiler.subtitle), (discovery, artifact.compiler.discovery)):
        path = _file(Path(path).parent, Path(path).name)
        if _fingerprint(path.name, _read(path)) != fingerprint.model_dump():
            raise ArtifactValidationError("native source fingerprint changed")
    if _code_fingerprints() != [f.model_dump() for f in artifact.compiler.code_files]:
        raise ArtifactValidationError("native compiler fingerprint changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subtitle", required=True, type=Path)
    parser.add_argument("--discovery", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--content-model", help="local model override for note only; preserves summary stage")
    args = parser.parse_args()
    try:
        client = OpenAIJsonClient.from_edu()
        content_client = replace(client, model=args.content_model) if args.content_model else client
        path = compile_native_video(subtitle=args.subtitle, discovery=args.discovery, output=args.output,
            client=client, stage_clients={"knowledge_note": content_client},
            on_stage=lambda message: print(message, flush=True))
        artifact = load_video_artifact(path)
        print(json.dumps({"artifact": str(path), "generation": artifact.content_sha256,
            "quality": artifact.quality, "segments": len(artifact.transcript.segments),
            "chapters": [c.model_dump() for c in artifact.chapters],
            "llm_total_tokens": sum(run.total_tokens for run in artifact.compiler.llm_runs)}, ensure_ascii=False, indent=2))
        return 0
    except (ArtifactValidationError, OSError, ValueError) as exc:
        print(f"Native compilation rejected: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
