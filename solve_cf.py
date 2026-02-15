"""
Cloudflare 过盾脚本

用途:
1. 复用系统代理配置访问 chatgpt.com
2. 等待 Cloudflare 质询自动完成
3. 提取 cf_clearance 并写入数据库 settings 表
"""
import argparse
import asyncio
import logging
import sys
from typing import Dict, Optional
from urllib.parse import unquote, urlparse

from app.database import AsyncSessionLocal
from app.services.settings import settings_service


logger = logging.getLogger("solve_cf")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

TARGET_URL = "https://chatgpt.com"
CHROMIUM_BASE_ARGS = [
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-sandbox",
]
CF_CHALLENGE_MARKERS = (
    "_cf_chl_opt",
    "cf-challenge",
    "managed challenge",
    "cf challenge",
    "ctype: 'managed'",
    'ctype: "managed"',
)


def _is_cloudflare_challenge(page_text: str) -> bool:
    if not page_text:
        return False
    lowered = page_text.lower()
    return any(marker in lowered for marker in CF_CHALLENGE_MARKERS)


def _get_chromium_args() -> list[str]:
    args = list(CHROMIUM_BASE_ARGS)
    # Windows 下 --single-process 容易导致 Chromium 提前退出
    if sys.platform.startswith("linux"):
        args.append("--single-process")
    return args


def _build_playwright_proxy(proxy_url: str) -> Dict[str, str]:
    parsed = urlparse(proxy_url)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError("代理地址格式无效")

    scheme = parsed.scheme.lower()
    if scheme == "socks5h":
        scheme = "socks5"
    if scheme not in {"http", "https", "socks5"}:
        raise ValueError("代理协议仅支持 http/https/socks5/socks5h")

    port = parsed.port
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "socks5":
            port = 1080
        else:
            port = 80

    proxy: Dict[str, str] = {"server": f"{scheme}://{parsed.hostname}:{port}"}
    if parsed.username:
        proxy["username"] = unquote(parsed.username)
    if parsed.password:
        proxy["password"] = unquote(parsed.password)
    return proxy


async def _load_proxy_for_browser() -> Optional[Dict[str, str]]:
    async with AsyncSessionLocal() as db_session:
        proxy_config = await settings_service.get_proxy_config(db_session)

    if not proxy_config.get("enabled"):
        return None

    proxy_url = (proxy_config.get("proxy") or "").strip()
    if not proxy_url:
        logger.warning("代理已启用但地址为空，将不使用代理")
        return None

    proxy = _build_playwright_proxy(proxy_url)
    logger.info(f"浏览器将使用代理: {proxy.get('server')}")
    return proxy


async def _save_cf_clearance(value: str) -> bool:
    async with AsyncSessionLocal() as db_session:
        return await settings_service.set_cf_clearance(db_session, value)


async def solve_cf(timeout_seconds: int, headless: bool) -> int:
    try:
        from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        logger.error("未安装 playwright，请先执行: pip install playwright && playwright install chromium")
        return 2

    logger.info("开始执行 Cloudflare 过盾流程")
    try:
        proxy = await _load_proxy_for_browser()
    except Exception as e:
        logger.error(f"加载代理配置失败: {e}")
        return 1

    cf_clearance: Optional[str] = None
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                headless=headless,
                proxy=proxy,
                args=_get_chromium_args()
            )
            context = await browser.new_context()
            page = await context.new_page()

            try:
                logger.info(f"访问 {TARGET_URL}")
                await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=45000)
            except PlaywrightTimeoutError:
                logger.warning("页面首次加载超时，继续轮询 cookie")

            deadline = asyncio.get_running_loop().time() + max(5, timeout_seconds)
            while asyncio.get_running_loop().time() < deadline:
                cookies = await context.cookies(TARGET_URL)
                matched_cookie = next(
                    (
                        cookie.get("value")
                        for cookie in cookies
                        if cookie.get("name") == "cf_clearance" and cookie.get("value")
                    ),
                    None
                )
                if matched_cookie:
                    cf_clearance = matched_cookie
                    break

                page_text = await page.content()
                if _is_cloudflare_challenge(page_text):
                    logger.info("仍在 Cloudflare 质询阶段，继续等待...")
                else:
                    logger.info("页面暂未检测到质询标记，继续等待 cf_clearance...")
                await page.wait_for_timeout(1000)

            await context.close()
            await browser.close()
    except Exception as e:
        logger.error(f"过盾执行失败: {e}")
        return 1

    if not cf_clearance:
        logger.error("在超时时间内未获取到 cf_clearance，请重试或延长等待时间")
        return 1

    saved = await _save_cf_clearance(cf_clearance)
    if not saved:
        logger.error("cf_clearance 获取成功，但写入数据库失败")
        return 1

    logger.info("cf_clearance 获取并写入成功")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cloudflare 过盾并写入 cf_clearance")
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="等待过盾完成的超时时间（秒），默认 30"
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="使用有头模式运行 Chromium（默认无头）"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return asyncio.run(solve_cf(timeout_seconds=args.timeout, headless=not args.headed))


if __name__ == "__main__":
    sys.exit(main())
