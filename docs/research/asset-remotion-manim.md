# 素材环节调研：Remotion vs Manim

> 调研日期：2026-10-04
> 背景：做**知识类视频**，已有剪辑（OpenChatCut）、配音（Kokoro）、生图（ChatGPT 网页）、转写（faster-whisper），缺"素材从哪来"。
> 约束：本地免费优先（RTX 4060 Laptop 8GB / Windows / 个人使用）。

## 一句话结论

两者**不冲突、互补**：

- **Manim**（Python）→ 数理类动画：公式推导、函数曲线、几何演示、流程图解，3Blue1Brown 风格
- **Remotion**（React/TS）→ 通用动态图形：标题包装、字幕条、数据卡片、代码打字效果、模板化批量出片

个人使用两者都**免费**。先各跑一个 30 秒 POC 再定主次（见文末）。

## Remotion

- **是什么**：用 React 组件写视频，每帧就是一个 React 渲染；无头 Chrome 逐帧截图 + FFmpeg 合成 MP4。附带 Remotion Studio（实时预览/调试）。
- **官网**：<https://www.remotion.dev>，文档 <https://www.remotion.dev/docs>
- **许可**（关键，非 OSI 开源，是 source-available 自定义许可）：
  - **Free License**：个人、≤3 人的营利组织、非营利组织、评估用途 —— 免费且**允许商用、允许自动化出片**（官方条款原文："Free License Users may build automations without purchasing Renders"）
  - 4 人以上公司才需要 Company License（$25/席位/月 + 自动化 $0.01/render，$100/月起）
  - 个人做视频发布赚钱：允许
  - 来源：<https://www.remotion.dev/docs/license/pricing>、<https://github.com/remotion-dev/remotion/blob/main/LICENSE.md>
- **本地/离线**：渲染完全在本机（headless Chrome + 内置 FFmpeg），不强制云服务；云渲染（Lambda）是可选项
- **Windows**：一等公民，`npx remotion render` 直接跑
- **适合生成的素材**：
  - 片头/片尾、标题卡、章节转场
  - 逐字字幕/动态排版（与配音对齐可吃时间戳数据）
  - 代码打字演示、UI/网页演示动画
  - 数据卡片、图表动画（可由脚本注入 JSON 驱动 → 批量出片）
- **优点**：Web 技术栈（HTML/CSS/SVG/Canvas/WebGL 都能上），表现力上限高；LLM 写 React 代码质量高 → AI 生成素材友好；模板化 + 数据驱动天然适合流水线
- **缺点**：不是 OSI 开源（团队长大要付费，个人无碍）；渲染吃内存（headless Chrome），长视频占盘；学习前提是 React 基础
- **依赖**：Node.js（本机已有）

## Manim

- **是什么**：程序化数学动画引擎，3Blue1Brown 视频同款。写 Python 场景脚本 → 渲染 MP4。
- **两个分支**（官方明确警告不要混装）：
  - **ManimCE**（社区版，PyPI 包名 `manim`，MIT 许可）：稳定、有参考手册、文档全，**推荐大多数用户**
  - **ManimGL**（3b1b 原版，PyPI 包名 `manimgl`）：OpenGL 渲染、交互式开发（`-se` 实时预览），但文档少、Windows 上高分辨率渲染有坑（社区反馈 720p 以上不稳）
- **官网**：<https://www.manim.community>（CE）、<https://github.com/3b1b/manim>（GL）
- **许可**：**MIT，完全免费无限制**（两个分支都是）
- **本地/离线**：完全本地渲染，无任何网络依赖
- **Windows 依赖**：
  - `pip install manim`（CE，wheel 可直接装）
  - FFmpeg（本机 encode 环节本来就要配）
  - LaTeX（**可选**）：只有用 `MathTex` 渲染公式才需要，Windows 装 MiKTeX 即可；不用公式可完全不装
- **适合生成的素材**：
  - 公式推导/高亮逐步展开
  - 函数曲线、坐标系、数据可视化
  - 几何/算法流程图解（箭头、方框、逐步出现）
  - 矩阵变换、向量、3D 演示
- **优点**：数学表现力最强、MIT 干净、纯 Python（和现有脚本工作流同语言）、AI 生成 scene 代码的语料充足
- **缺点**：只擅长"讲解型图解"，做不了片头包装/排版设计感；中文注意点见下
- **中文注意**：`Text` 走 Pango，直接支持系统中文字体 ✅；`MathTex`/`Tex` 走 LaTeX，中文要配 xelatex+ctex（麻烦，建议公式保持英文，讲解中文用 `Text`）

## 对比表

| 维度 | Remotion | ManimCE |
|---|---|---|
| 语言 | React / TypeScript | Python |
| 许可 | 自定义（个人/≤3人免费，允许商用+自动化） | MIT（完全自由） |
| 渲染 | headless Chrome（帧截图）+ FFmpeg | Cairo（CPU）+ FFmpeg |
| GPU 利用 | 一般（可开 Chromium 硬件加速） | 一般（GL 分支才用 GPU） |
| 素材风格 | 包装/排版/动态图形/代码演示 | 数学图解/公式/图表 |
| 中文 | CSS 字体，无障碍 | Text 无障碍；LaTeX 公式要折腾 |
| AI 生成代码 | 语料多，质量高 | 语料多，质量高 |
| 长视频渲染 | 较慢（内存占用高） | 中等 |
| 输出 | MP4（可直接进 OpenChatCut `import_media`） | MP4（同左） |

## 补充：Remotion 官方 AI Skills（2026-10-04 核实）

**属实且规模超预期**：

- 官方文档专页：<https://www.remotion.dev/docs/ai/skills>，GitHub 仓库 `remotion-dev/skills`（4.8k star，agentskills.io 标准 = 纯 Markdown SKILL.md，任何支持 skills 的 agent 可用）
- 官方维护 12 个 skill：`remotion-best-practices`（总纲）、`remotion-create`、`remotion-markup`、`remotion-studio`、`remotion-render`、`remotion-maps`、`remotion-captions`、`remotion-saas`、`remotion-interactivity`、`remotion-docs`（查 API 文档）、`remotion-upgrade`、`remotion-multimedia`
- 一条命令安装：`npx skills add remotion-dev/skills`
- **官方文档明确点名支持 OpenCode**（"Claude Code, Codex, Kimi Code and OpenCode"）
- 生态外围：官方另设 Claude Code / Codex / Kimi Code 插件仓库；社区有 `iart-ai/motion-skills`（50 个动效包）、配音驱动讲解视频 skill（word 级配音对齐，正对知识类视频场景）

**对选型的影响**：Remotion 的 AI 上手成本被官方 skills 大幅拉低，而 Manim 无官方 skills（仅社区）。**POC 改为 Remotion 先行**，Manim 缓后。

## 其他候选（一句话带过）

- **Motion Canvas**（TypeScript，MIT）：介于两者之间，偏插值动画/时间线，可作 Remotion 的开源替代备选
- **OBS 录屏 + 剪辑**：屏幕操作类素材的零成本来源
- **Mermaid/D2 图表 → SVG 截帧**：流程图类静态/半静态素材的轻量路子

## 建议的下一步（待定）

1. 各做一个 30 秒 POC（同一主题各拍一段），实测渲染速度和写码手感
2. POC 验收后再决定：主用哪个、另一个是否保留为特定场景工具
3. 两个的产物统一走 OpenChatCut `import_media` 入剪辑台
