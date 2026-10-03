"""本地转写：faster-whisper → .srt 字幕 + 词级时间戳 .json

用法:
    python scripts/transcribe/cli.py <输入音视频> [选项]

选项:
    --model     模型，默认 Systran/faster-whisper-base（权重已在本机 HF 缓存）
    --language  语言代码 (zh/en/...)，默认自动检测
    --out-dir   输出目录，默认 workdir/transcribe/<输入文件名去扩展>

示例:
    python scripts/transcribe/cli.py path/to/video.mp4
    python scripts/transcribe/cli.py voice.wav --language en
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_MODEL = "Systran/faster-whisper-base"


def format_timestamp(seconds: float) -> str:
    """秒 → SRT 时间戳 HH:MM:SS,mmm"""
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def build_srt(segments: list[dict]) -> str:
    lines = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(
            f"{format_timestamp(segment['start'])} --> {format_timestamp(segment['end'])}"
        )
        lines.append(segment["text"].strip())
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="faster-whisper 本地转写")
    parser.add_argument("input", help="输入音视频文件")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="模型 id 或本地路径")
    parser.add_argument("--language", default=None, help="语言代码，如 zh/en；默认自动检测")
    parser.add_argument("--out-dir", default=None, help="输出目录")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"错误: 输入文件不存在: {input_path}", file=sys.stderr)
        return 1

    if args.out_dir:
        out_dir = Path(args.out_dir)
    else:
        out_dir = Path("workdir/transcribe") / input_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    from faster_whisper import WhisperModel

    print(f"加载模型: {args.model}", file=sys.stderr)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    print(f"转写: {input_path}", file=sys.stderr)
    segments_iter, info = model.transcribe(
        str(input_path),
        language=args.language,
        word_timestamps=True,
    )

    segments = []
    for segment in segments_iter:
        words = [
            {"start": round(word.start, 3), "end": round(word.end, 3), "word": word.word}
            for word in (segment.words or [])
        ]
        segments.append(
            {
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": segment.text,
                "words": words,
            }
        )

    payload = {
        "source": str(input_path.resolve()),
        "model": args.model,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "duration": round(info.duration, 3),
        "segments": segments,
    }

    json_path = out_dir / f"{input_path.stem}.json"
    srt_path = out_dir / f"{input_path.stem}.srt"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    srt_path.write_text(build_srt(segments), encoding="utf-8")

    word_count = sum(len(s["words"]) for s in segments)
    print(
        f"完成: {len(segments)} 段, {word_count} 词, "
        f"检测语言={info.language} ({info.language_probability:.0%})",
        file=sys.stderr,
    )
    print(json_path)
    print(srt_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
