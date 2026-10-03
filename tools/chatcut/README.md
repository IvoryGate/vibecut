# tools/chatcut — ChatCut 媒体导入助手

## upload-media.mjs

- **来源**: [ChatCut-Inc/agent-plugin](https://github.com/ChatCut-Inc/agent-plugin) `claude/skills/asset-import/scripts/upload-media.mjs`（vendored，main 分支 2026-10-03 快照）
- **用途**: 把本地媒体（图片/视频/音频）经 loopback helper 导入 ChatCut 项目素材池，配合 MCP `import_media` 使用
- **依赖**: Node.js 18+、ffmpeg、ffprobe

## 用法

1. 通过 MCP 调 `import_media({action: "create_session"})` 拿 `token` 和 `endpoint`（有效期 30 分钟）
2. 运行（最多 4 个文件一批）：

```bash
node tools/chatcut/upload-media.mjs --token <token> --endpoint <url> file1.png file2.png ...
```

3. stdout 返回 JSON，含各文件 `assetId`，用于后续编辑工具

## 备注

- OpenChatCut（本地版）不需要此脚本，本地导入通路不同
- 仅在用 ChatCut 云端 MCP 时需要；`opencode.json` 中 chatcut 当前为 `enabled: false`
