"""Kokoro TTS worker — 运行于 english-channel 的 kokoro-env 中，由 cli.py 启动。

调用模式参照 english-channel 的 workspace/runtime/tts-audition/audition.py：
单次加载模型 → 生成 → 写 WAV → 释放；确定性 seed。
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", required=True)
    parser.add_argument("--voice", default="af_heart")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--lang-code", default="a")
    parser.add_argument("--seed", type=int, default=20260908)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    import numpy as np
    import soundfile as sf
    import torch
    from kokoro import KPipeline

    torch.set_num_threads(8)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    started = time.perf_counter()
    pipeline = KPipeline(lang_code=args.lang_code, device="cpu", repo_id="hexgrad/Kokoro-82M")

    chunks = [
        result.audio.detach().cpu().numpy()
        for result in pipeline(args.text, voice=args.voice, speed=args.speed)
    ]
    if not chunks:
        print(json.dumps({"error": "模型未产出音频"}))
        return 1
    wav = np.concatenate(chunks)
    generation_sec = round(time.perf_counter() - started, 3)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 24000
    sf.write(out_path, wav, sample_rate)

    meta = {
        "engine": "kokoro-82m",
        "voice": args.voice,
        "speed": args.speed,
        "lang_code": args.lang_code,
        "seed": args.seed,
        "sample_rate": sample_rate,
        "duration_sec": round(len(wav) / sample_rate, 3),
        "generation_sec": generation_sec,
        "text": args.text,
    }
    out_path.with_suffix(".json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
