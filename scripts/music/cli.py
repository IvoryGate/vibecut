"""音乐 CLI：MusicGen 文字生成 BGM + 侧链压低（duck）合成

用法:
    python scripts/music/cli.py gen "calm piano loop for explainer video" --seconds 30 --out workdir/music/bgm.wav
    python scripts/music/cli.py duck --video out/x.mp4 --music workdir/music/bgm.wav --out out/x-bgm.mp4
    python scripts/music/cli.py duck ... --music-vol 0.22        # BGM 底噪（相对音量，默认 0.22）

环境:
    gen 推理需要 torch+cu126，本机现成位置是 D:/Anaconda/envs/GPTSoVits_py310（已有
    transformers 4.50，零新装包）。若当前解释器缺 torch，脚本自动用该解释器重入。
    模型缓存默认 HF_HOME=workdir/hf-cache（F 盘，不进 C 盘、不入 git）。
    duck 只依赖 ffmpeg，任何解释器可跑。
"""

from __future__ import annotations

import argparse
import math
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FALLBACK_PY = Path(r"D:/Anaconda/envs/GPTSoVits_py310/python.exe")
MODEL_ID = "facebook/musicgen-stereo-small"
SR = 32000  # MusicGen 恒定采样率

# 模型缓存落 F 盘 workdir（C 盘紧张，且 workdir 已 gitignored）
os.environ.setdefault("HF_HOME", str(REPO / "workdir" / "hf-cache"))


def _ensure_torch() -> None:
    """gen 需要 torch；当前环境没有就用 GPTSoVits 环境重入自己。"""
    try:
        import torch  # noqa: F401
        return
    except ImportError:
        pass
    if not FALLBACK_PY.exists():
        print(f"错误: 缺 torch 且找不到备用解释器 {FALLBACK_PY}", file=sys.stderr)
        sys.exit(1)
    if Path(sys.executable).resolve() == FALLBACK_PY.resolve():
        print("错误: 备用解释器也没有 torch", file=sys.stderr)
        sys.exit(1)
    os.execv(str(FALLBACK_PY), [str(FALLBACK_PY), str(Path(__file__).resolve()), *sys.argv[1:]])


def cmd_gen(args: argparse.Namespace) -> int:
    _ensure_torch()
    import soundfile as sf
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"模型: {args.model} | 设备: {device} | 缓存: {os.environ.get('HF_HOME')}", file=sys.stderr)

    torch.manual_seed(args.seed)
    processor = AutoProcessor.from_pretrained(args.model)
    model = MusicgenForConditionalGeneration.from_pretrained(args.model)
    model.to(device)

    inputs = processor(text=[args.prompt], padding=True, return_tensors="pt").to(device)
    max_new_tokens = int(args.seconds * 50)  # MusicGen ≈ 50 token/秒
    print(f"生成中: {args.seconds}s ({max_new_tokens} tokens)...", file=sys.stderr)
    with torch.inference_mode():
        audio = model.generate(
            **inputs,
            do_sample=True,
            guidance_scale=3.0,
            max_new_tokens=max_new_tokens,
        )

    # audio: stereo (1, 2, T) / mono (1, 1, T) -> (T, ch)
    wav = audio[0].cpu().numpy().T
    peak = float(abs(wav).max()) or 1.0
    wav = (wav / peak) * 0.95  # 峰值归一到 -0.45dB，便于后续混音

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out, wav, SR)
    print(f"完成: {out} ({wav.shape[0] / SR:.1f}s, {wav.shape[1]}ch)")
    return 0


def _ffprobe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def cmd_duck(args: argparse.Namespace) -> int:
    """BGM 循环铺满全片 → 首尾 fade → 被人声侧链压低 → 与原声混合。"""
    video = Path(args.video)
    music = Path(args.music)
    out = Path(args.out)
    dur = _ffprobe_duration(video)
    music_dur = _ffprobe_duration(music)
    loops = max(0, math.ceil(dur / music_dur) - 1)  # stream_loop 次数（有限循环，避免悬空输入）

    fade_out_start = max(0.0, dur - 2.5)
    vol = args.music_vol
    fc = (
        f"[1:a]volume={vol},"
        f"afade=t=in:d=1.5,afade=t=out:st={fade_out_start:.3f}:d=2.5[bgm];"
        f"[bgm][0:a]sidechaincompress=threshold=0.02:ratio=8:attack=20:release=600[duck];"
        f"[0:a][duck]amix=inputs=2:duration=first:normalize=0[mix]"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", str(video),
        "-stream_loop", str(loops), "-i", str(music),
        "-filter_complex", fc,
        "-map", "[mix]", "-map", "0:v",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
        str(out),
    ]
    print(" ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)
    print(f"完成: {out} ({dur:.1f}s, 循环 {loops + 1} 段 BGM, 音量 {vol})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="MusicGen 文生 BGM + 侧链配乐")
    sub = p.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("gen", help="文字生成 BGM")
    g.add_argument("prompt", help="英文描述效果最好")
    g.add_argument("--seconds", type=int, default=30)
    g.add_argument("--out", default="workdir/music/bgm.wav")
    g.add_argument("--seed", type=int, default=20261005)
    g.add_argument("--model", default=MODEL_ID)
    g.set_defaults(func=cmd_gen)

    d = sub.add_parser("duck", help="BGM 垫进视频并被侧链压低")
    d.add_argument("--video", required=True)
    d.add_argument("--music", required=True)
    d.add_argument("--out", required=True)
    d.add_argument("--music-vol", type=float, default=0.22)
    d.set_defaults(func=cmd_duck)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
