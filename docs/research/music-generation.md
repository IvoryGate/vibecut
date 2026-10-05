# 音乐环节调研：本地文生 BGM

日期：2026-10-05 ｜ 环节：music ｜ 结论：**MusicGen stereo-small（transformers 原生）**

## 需求

- 输入一句话描述 → 输出一段可做背景音乐的 BGM（wav），本地生成、免费
- 用途：给成片垫底乐（配合 sidechain duck 压在人声下），30s 左右可循环
- 硬约束：RTX 4060 8GB（实测空闲 6.8G）；不进 C 盘缓存；模型权重不入库

## 候选对比

| 路线 | 模型/工具 | 体积 | 音质 | 依赖 | 结论 |
|---|---|---|---|---|---|
| **MusicGen**（Meta） | `facebook/musicgen-stereo-small` | 权重 ≈2.5GB（一次性） | 32kHz 立体声（≈MP3 级），BGM 够用 | `transformers` 4.50 **现成**，零新装包 | ✅ 选中 |
| Stable Audio Open（Stability） | `stabilityai/stable-audio-open-1.0` | ≈2.6GB + diffusers ≈200MB | 44.1kHz 立体声（CD 级），上限更高 | 需装 diffusers、首次编译 VAE 可能踩坑 | 备选：音质不够时升级 |
| ACE-Step / YuE 等歌曲生成 | 3.5B+ 全曲模型 | 7GB+ | 高（能出人声演唱） | 显存吃紧、依赖复杂 | ❌ 超出 BGM 需求 |
| 传统 MIDI 音色库 | fluidsynth + soundfont | 几十 MB | 机械呆板（电子琴自动伴奏感） | 零 AI 依赖 | ❌ 质量不可接受 |

## 选型依据（事实记录）

1. **零依赖**：`D:/Anaconda/envs/GPTSoVits_py310` 已有 `torch 2.11.0+cu126`（CUDA 可用）、
   `transformers 4.50.0`、`soundfile/scipy/numpy` —— MusicGen 是 transformers 原生支持的
   任务（`MusicgenForConditionalGeneration`），无需安装任何包，也无需改动该环境
   （所有新依赖都显式 import，进程隔离，不污染 GPT-SoVits 自身）。
2. **显存**：small 档 300M 参数 + T5 文本编码器，fp32 推理 ≈3-4GB，6.8G 空闲可跑。
   未选 medium/large（fp32 超 8GB，需量化折腾）。
3. **立体声**：stereo-small 与 mono-small 权重体积相近，立体声对 BGM 更值。
4. **缓存位置**：`HF_HOME` 默认指向 `workdir/hf-cache`（F 盘，gitignored），
   避免默认 `~/.cache/huggingface` 撑爆 C 盘（C 曾到 98% 满）。

## 用法（scripts/music/cli.py）

```bash
# 生成（首次运行自动下载权重到 workdir/hf-cache，一次性 ≈2.5GB）
python scripts/music/cli.py gen "calm piano ambient loop for knowledge video" \
  --seconds 30 --out workdir/music/bgm.wav

# 配乐合成：BGM 循环铺满全片 + 首尾 fade + 侧链压在人声下
python scripts/music/cli.py duck --video out/explainer-bayes.mp4 \
  --music workdir/music/bgm.wav --out out/explainer-bayes-bgm.mp4 --music-vol 0.22
```

## 后续可做（本轮不做）

- 曲风微调：保存 seed 做 A/B（cli 已带 `--seed`）
- 节拍对齐：生成后接 beat-sync 环节做卡点剪辑
- 音乐检索库路线：本地向量检索现成 CC 音乐（生成质量不够时的退路）
