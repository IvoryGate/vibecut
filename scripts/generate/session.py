"""常驻浏览器会话（按天为单位）—— 每天开工启动一次，收工 Ctrl+C 关闭。

启动内容：
- Playwright 自带 Chromium + `.browser-profile`（登录态持久化，免登录）
- 本地 CDP 调试端口（默认 9333，可用环境变量 VIBECUT_CDP_PORT 覆盖）
- 打开 chatgpt.com

之后 `scripts/generate/cli.py` 会通过 CDP **附着**到本会话执行生图，
不再新开窗口、不再走登录检测，生成完浏览器保持打开，直到收工。

用法:
    python scripts/generate/session.py     # 开工：启动并保持
    Ctrl+C                                  # 收工：关闭浏览器

遵循 AGENTS.md §5：本脚本不涉及内容输入，无停顿要求；输入行为在 cli.py。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

CDP_PORT = int(os.environ.get("VIBECUT_CDP_PORT", "9333"))
PROFILE_DIR = Path(".browser-profile")
CHATGPT_HOME = "https://chatgpt.com/"
STARTUP_WAIT_SEC = 20


def port_alive(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def cdp_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=2) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    if port_alive(CDP_PORT):
        print(f"会话已在运行（CDP 端口 {CDP_PORT}），无需重复启动")
        return 0

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        executable = p.chromium.executable_path

    cmd = [
        executable,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--lang=zh-CN",
        "--window-size=1440,900",
        CHATGPT_HOME,
    ]
    print(f"启动浏览器会话... (CDP: http://127.0.0.1:{CDP_PORT})")
    process = subprocess.Popen(cmd)

    deadline = time.time() + STARTUP_WAIT_SEC
    while time.time() < deadline:
        if cdp_ready(CDP_PORT):
            break
        if process.poll() is not None:
            print(f"错误: 浏览器进程退出（code {process.returncode}）", file=sys.stderr)
            return 1
        time.sleep(0.5)
    else:
        print(f"错误: CDP 端口 {CDP_PORT} 在 {STARTUP_WAIT_SEC}s 内未就绪", file=sys.stderr)
        process.terminate()
        return 1

    print("会话就绪。生图任务：python scripts/generate/cli.py --prompt \"...\"")
    print("收工请按 Ctrl+C 关闭浏览器（登录态已持久化，明天免登录）。")
    try:
        while process.poll() is None:
            time.sleep(1)
        print("浏览器已退出。")
    except KeyboardInterrupt:
        print("\n收工：关闭浏览器会话...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
