"""Isolated real Faster Whisper decoding, compatible with EDU Python 3.11."""
from __future__ import annotations
import argparse
import importlib.metadata
from pathlib import Path
from app.domains.video_learning.media import digest, _probe, _write


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--media-sha256", required=True)
    args = parser.parse_args()
    from faster_whisper import WhisperModel
    model = WhisperModel(str(args.model), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
    stream, info = model.transcribe(str(args.audio), language=None, vad_filter=True, beam_size=5)
    segments = []
    for raw in stream:
        text = raw.text.strip()
        if text and raw.end > raw.start:
            segments.append({"start": round(float(raw.start), 3), "end": round(float(raw.end), 3), "text": text})
            if len(segments) % 25 == 0:
                print(f"ASR segments={len(segments)} second={raw.end:.1f}", flush=True)
    _write(args.output, {"transcript": "\n".join(x["text"] for x in segments), "segments": segments,
            "asr_model_sha256": digest(args.model / "model.bin"),
            "asr_run": {"provider": "faster-whisper", "model": args.model.name.removeprefix("faster-whisper-"), "language": info.language, "device": "cpu",
                        "compute_type": "int8", "package_version": importlib.metadata.version("faster-whisper"),
                        "media_sha256": args.media_sha256, "audio_sha256": digest(args.audio),
                        "audio_duration": _probe(args.audio)["duration"]}})


if __name__ == "__main__":
    main()
