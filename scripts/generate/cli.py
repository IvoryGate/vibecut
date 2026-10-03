"""画面生成：通过常驻会话（session.py）驱动 ChatGPT 网页版生成图片并下载

工作模式（AGENTS.md §4/§5）：
- **默认附着模式**：连接 session.py 启动的常驻浏览器（CDP 端口 9333），
  不新开窗口、不走登录检测；生成完浏览器保持打开，直到收工 Ctrl+C。
  session 未启动时会提示先启动，不悄悄弹窗。
- **--standalone**：无 session 时独立启动一次浏览器（用于新机器首次登录等场景）。

对话策略 --chat（防上下文污染）：
- new（默认）：每次生成开一个新对话
- continue：续写当前对话
- <URL>：指定对话继续（同一场景的迭代图放同一个对话）

随机停顿规范（AGENTS.md §5）：分段逐字输入，输入→提交区间真随机停顿
（secrets 系统熵、无固定种子），风控挑战退避重试。

用法:
    python scripts/generate/cli.py --prompt "图片提示词"
    python scripts/generate/cli.py --prompt-file prompt.txt --chat https://chatgpt.com/c/xxx
"""

from __future__ import annotations

import argparse
import base64
import json
import secrets
import sys
import time
from datetime import datetime
from pathlib import Path

PROFILE_DIR = Path(".browser-profile")
CDP_URL = "http://127.0.0.1:9333"
LOGIN_WAIT_SEC = 300        # standalone 首次登录最多等 5 分钟
IMAGE_WAIT_SEC = 240        # 图片生成最长等 4 分钟
CHALLENGE_MAX_RETRY = 2     # 风控挑战最大重试次数（退避后）

IMG_ALT = "已生成图像"


def jitter(lo: float, hi: float) -> float:
    """区间内真随机（系统熵），不设固定种子，避免形成时序指纹"""
    return secrets.SystemRandom().uniform(lo, hi)


def human_pause(lo: float = 2.5, hi: float = 6.5) -> float:
    """输入→提交之间的人类化随机停顿，返回实际停顿秒数（写入 meta 供审计）"""
    seconds = jitter(lo, hi)
    time.sleep(seconds)
    return seconds


def type_like_human(page, text: str) -> None:
    """分段逐字输入：段长、每字延迟、段间微停顿全部随机"""
    box = page.get_by_role("textbox", name="询问 ChatGPT").first
    box.click()
    position = 0
    while position < len(text):
        chunk_len = int(jitter(5, 14))
        chunk = text[position:position + chunk_len]
        box.type(chunk, delay=int(jitter(30, 85)))
        position += chunk_len
        if position < len(text):
            time.sleep(jitter(0.06, 0.28))


def dismiss_dialogs(page) -> None:
    """登录/升级引导弹窗会挡住输入框：随机停顿后逐个关闭"""
    time.sleep(jitter(1.0, 2.5))
    for _ in range(3):
        if page.locator('[role="dialog"]').count() == 0:
            break
        page.keyboard.press("Escape")
        time.sleep(jitter(0.8, 1.8))


def logged_in(page) -> bool:
    """三条件判定：回到 chatgpt.com + 无「登录」按钮 + 输入框可见"""
    try:
        if "chatgpt.com" not in page.url:
            return False
        if page.get_by_role("button", name="登录").first.is_visible(timeout=1000):
            return False
        return page.get_by_role("textbox", name="询问 ChatGPT").first.is_visible(timeout=1000)
    except Exception:  # noqa: BLE001
        return False


def wait_for_login(page) -> bool:
    """standalone 模式等待用户完成登录（仅首次）"""
    if logged_in(page):
        return True
    print("检测到未登录：请在打开的浏览器窗口完成 ChatGPT 登录（最多等待 5 分钟）", flush=True)
    deadline = time.time() + LOGIN_WAIT_SEC
    while time.time() < deadline:
        time.sleep(jitter(1.5, 3.5))
        if logged_in(page):
            print("登录成功", flush=True)
            return True
    return False


def wait_for_image(page) -> bool:
    """等待图片生成完成；遇到风控挑战页则退避重试"""
    for attempt in range(CHALLENGE_MAX_RETRY + 1):
        try:
            page.locator(f'img[alt*="{IMG_ALT}"]').first.wait_for(
                state="visible", timeout=IMAGE_WAIT_SEC * 1000
            )
            return True
        except Exception:  # noqa: BLE001
            challenge = page.get_by_text("cloudflare_challenge").count() > 0
            if not challenge or attempt == CHALLENGE_MAX_RETRY:
                return False
            backoff = jitter(8.0, 16.0) * (attempt + 1)
            print(f"触发风控挑战，退避 {backoff:.1f}s 后重试（{attempt + 1}/{CHALLENGE_MAX_RETRY}）", flush=True)
            time.sleep(backoff)
            retry_btn = page.get_by_role("button", name="重试").first
            if retry_btn.count() > 0 and retry_btn.is_visible():
                retry_btn.click()
    return False


def extract_image(page) -> dict:
    """页面内把 blob 图片转 base64 取出"""
    payload = page.evaluate(
        """async () => {
            const img = [...document.querySelectorAll('img')]
                .find(i => (i.alt || '').includes('已生成图像'));
            if (!img) return JSON.stringify({error: 'image not found'});
            const blob = await (await fetch(img.src)).blob();
            const bytes = new Uint8Array(await blob.arrayBuffer());
            let binary = '';
            const chunk = 0x8000;
            for (let i = 0; i < bytes.length; i += chunk) {
                binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
            }
            return JSON.stringify({mime: blob.type, size: blob.size, b64: btoa(binary)});
        }"""
    )
    data = json.loads(payload)
    if isinstance(data, str):
        data = json.loads(data)
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


def run_generation(page, prompt: str, out_dir: Path) -> int:
    """在给定页面上执行一次生图：输入 → 随机停顿 → 发送 → 等图 → 下载"""
    out_dir.mkdir(parents=True, exist_ok=True)

    dismiss_dialogs(page)
    type_like_human(page, prompt)
    pause = human_pause(2.5, 6.5)          # 关键：输入→发送随机停顿
    page.get_by_role("textbox", name="询问 ChatGPT").first.press("Enter")

    if not wait_for_image(page):
        print("错误: 等待图片超时或风控未通过", file=sys.stderr)
        return 1

    data = extract_image(page)
    chat_url = page.url

    ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(data["mime"], "bin")
    out_image = out_dir / f"image.{ext}"
    out_image.write_bytes(base64.b64decode(data["b64"]))

    meta = {
        "prompt": prompt,
        "mime": data["mime"],
        "size": data["size"],
        "chat_url": chat_url,
        "send_pauses_sec": [round(pause, 2)],
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"完成: {out_image} ({data['size']} bytes)", flush=True)
    print(f"对话: {chat_url}", flush=True)
    print(out_image)
    return 0


def select_attached_page(context, chat: str):
    """按 --chat 策略选择/打开工作页

    new      → 复用第一个 chatgpt 页或新开，导航到首页（新对话）
    continue → 复用当前 chatgpt 页（不导航）
    <URL>    → 复用第一个 chatgpt 页或新开，导航到指定对话
    """
    chatgpt_pages = [pg for pg in context.pages if pg.url.startswith("http")]
    chatgpt_pages = [pg for pg in chatgpt_pages if "chatgpt.com" in pg.url]
    page = chatgpt_pages[0] if chatgpt_pages else context.new_page()

    if chat == "continue":
        return page
    target = "https://chatgpt.com/" if chat == "new" else chat
    page.goto(target, wait_until="domcontentloaded", timeout=60000)
    time.sleep(jitter(1.0, 2.0))
    return page


def main() -> int:
    parser = argparse.ArgumentParser(description="ChatGPT 网页版图片生成")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--prompt", help="图片提示词")
    source.add_argument("--prompt-file", help="从 UTF-8 文本文件读取提示词")
    parser.add_argument("--out-dir", default=None, help="输出目录，默认 workdir/generate/<时间戳>/")
    parser.add_argument(
        "--chat",
        default="new",
        help="对话策略: new（默认，新对话）| continue（续当前）| <对话URL>",
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="独立启动浏览器（不走 session，用于新机器首次登录）",
    )
    args = parser.parse_args()

    prompt = (
        Path(args.prompt_file).read_text(encoding="utf-8").strip()
        if args.prompt_file
        else args.prompt.strip()
    )
    if not prompt:
        parser.error("提示词为空")

    out_dir = (
        Path(args.out_dir)
        if args.out_dir
        else Path("workdir/generate") / datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        if args.standalone:
            # 独立模式：自己拥有浏览器生命周期（首次登录场景）
            ctx = None
            last_error = None
            for channel in (None, "msedge", "chrome"):  # 优先自带 Chromium
                for sandbox in (True, False):  # 优先开沙箱，避免 --no-sandbox 不受支持横条
                    try:
                        ctx = p.chromium.launch_persistent_context(
                            str(PROFILE_DIR),
                            channel=channel,
                            headless=False,
                            locale="zh-CN",
                            viewport={"width": 1440, "height": 900},
                            chromium_sandbox=sandbox,
                        )
                        break
                    except Exception as exc:  # noqa: BLE001
                        last_error = exc
                if ctx is not None:
                    break
            if ctx is None:
                print(f"错误: 无法启动浏览器: {last_error}", file=sys.stderr)
                return 1

            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto("https://chatgpt.com", wait_until="domcontentloaded", timeout=60000)

            if not wait_for_login(page):
                print("错误: 登录超时", file=sys.stderr)
                ctx.close()
                return 1
            result = run_generation(page, prompt, out_dir)
            ctx.close()
            return result

        # 附着模式（默认）：连接 session.py 的常驻浏览器
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL, timeout=3000)
        except Exception:  # noqa: BLE001
            print(
                "错误: 常驻会话未运行。请先启动：python scripts/generate/session.py",
                file=sys.stderr,
            )
            return 1

        context = browser.contexts[0]
        page = select_attached_page(context, args.chat)
        if not logged_in(page):
            print("错误: 会话登录态失效，请重启 session.py 并完成登录", file=sys.stderr)
            return 1

        # 注意：附着模式不调用 browser.close()/context.close()，
        # 只断开 CDP 连接（with 退出时 stop），浏览器保持打开供下一个任务复用。
        return run_generation(page, prompt, out_dir)


if __name__ == "__main__":
    sys.exit(main())
