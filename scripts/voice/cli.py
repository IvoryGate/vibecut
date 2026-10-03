"""配音 CLI：调用 english-channel 的 kokoro-env 生成语音

跨项目调用模式：本脚本运行在 vibecut 的 .venv 中（只做参数与进程管理），
实际模型推理由 english-channel 的隔离环境 kokoro-env 执行（子进程），
通过环境变量 HF_HOME 指向其本地权重缓存。

用法:
    python scripts/voice/cli.py "要朗读的文本"
    python scripts/voice/cli.py --text-file script.txt --voice am_fenrir
    python scripts/voice/cli.py "中文测试" --lang-code z

环境变量:
    VIBECUT_TTS_ROOT  english-channel 的 tts-audition 目录，
                      默认 H:\\english-channel\\workspace\\runtime\\tts-audition
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_TTS_ROOT = Path(r"H:\english-channel\workspace\runtime\tts-audition")
WORKER = Path(__file__).parent / "kokoro_worker.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Kokoro 本地配音")
    parser.add_argument("text", nargs="?", help="要朗读的文本")
    parser.add_argument("--text-file", help="从文本文件读取（UTF-8），与位置文本二选一")
    parser.add_argument("--voice", default="af_heart", help="音色 id，默认 af_heart")
    parser.add_argument("--speed", type=float, default=1.0, help="语速倍率")
    parser.add_argument(
        "--lang-code", default="a",
        help="KPipeline 语言码: a=英语(美) z=中文 j=日语，默认 a",
    )
    parser.add_argument("--seed", type=int, default=20260908, help="随机种子（可复现）")
    parser.add_argument("--out-dir", default=None, help="输出目录，默认 workdir/voice/kokoro-<voice>/")
    args = parser.parse_args()

    tts_root = Path(os.environ.get("VIBECUT_TTS_ROOT", str(DEFAULT_TTS_ROOT)))
    kokoro_python = tts_root / "kokoro-env" / "Scripts" / "python.exe"
    if not kokoro_python.exists():
        print(f"错误: 找不到 kokoro-env: {kokoro_python}", file=sys.stderr)
        print("可用 VIBECUT_TTS_ROOT 环境变量指向正确的 tts-audition 目录", file=sys.stderr)
        return 1

    if args.text_file and args.text:
        parser.error("位置文本与 --text-file 只能二选一")
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8").strip()
    else:
        text = (args.text or "").strip()
    if not text:
        parser.error("缺少要朗读的文本")

    out_dir = Path(args.out_dir) if args.out_dir else Path("workdir/voice") / f"kokoro-{args.voice}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_wav = out_dir / "out.wav"

    env = os.environ.copy()
    # 净化：PYTHONHOME 指向本仓库 venv 的基础解释器时，会让 kokoro-env(3.11)
    # 子进程错配 stdlib（SRE module mismatch）；PYTHONPATH 为外部工具链残留，一并剥离
    for var in ("PYTHONHOME", "UV_INTERNAL__PYTHONHOME", "PYTHONPATH"):
        env.pop(var, None)
    # kokoro-env 的权重与音色缓存在 english-channel 本地
    env["HF_HOME"] = str(tts_root / "cache" / "huggingface")
    env["PYTHONUTF8"] = "1"

    cmd = [
        str(kokoro_python), str(WORKER),
        "--text", text,
        "--voice", args.voice,
        "--speed", str(args.speed),
        "--lang-code", args.lang_code,
        "--seed", str(args.seed),
        "--out", str(out_wav),
    ]
    print(f"调用: {kokoro_python.name} (voice={args.voice}, speed={args.speed})", file=sys.stderr)
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8")

    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return result.returncode

    meta = json.loads(result.stdout.strip().splitlines()[-1])
    print(
        f"完成: {out_wav} ({meta['duration_sec']}s, 生成耗时 {meta['generation_sec']}s)",
        file=sys.stderr,
    )
    print(out_wav)
    return 0


if __name__ == "__main__":
    sys.exit(main())
