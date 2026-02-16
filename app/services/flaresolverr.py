"""
FlareSolverr 远程过盾服务
负责调用 FlareSolverr API 获取 cf_clearance 并支持后台自动刷新。
"""
import asyncio
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse, urlunparse
from datetime import datetime

from curl_cffi.requests import AsyncSession

from app.database import AsyncSessionLocal
from app.services.settings import (
    DEFAULT_CF_REFRESH_INTERVAL_MINUTES,
    settings_service,
)

logger = logging.getLogger(__name__)


class FlareSolverrService:
    """FlareSolverr 客户端服务"""

    TARGET_URL = "https://chatgpt.com"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    DEFAULT_MAX_TIMEOUT_MS = 120000
    IDLE_CHECK_SECONDS = 60
    FAILURE_RETRY_SECONDS = 120

    def __init__(self):
        self._lock = asyncio.Lock()
        self._running_task: Optional[asyncio.Task] = None
        self._loop_task: Optional[asyncio.Task] = None

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat(timespec="seconds")

    @staticmethod
    def _build_endpoint_candidates(url: str) -> list[str]:
        normalized = (url or "").strip()
        if not normalized:
            return []

        parsed = urlparse(normalized)
        if not parsed.scheme or not parsed.netloc:
            return [normalized]

        path = (parsed.path or "").rstrip("/")
        if not path:
            path = "/v1"

        base_endpoint = urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
        candidates = [base_endpoint]

        if path.endswith("/v1.request"):
            alt_path = path[: -len(".request")]
            candidates.append(urlunparse((parsed.scheme, parsed.netloc, alt_path, "", "", "")))
        elif path.endswith("/v1"):
            candidates.append(urlunparse((parsed.scheme, parsed.netloc, f"{path}.request", "", "", "")))
        elif path == "/v1":
            candidates.append(urlunparse((parsed.scheme, parsed.netloc, "/v1.request", "", "", "")))

        # 去重并保持顺序
        seen = set()
        unique_candidates = []
        for item in candidates:
            if item in seen:
                continue
            seen.add(item)
            unique_candidates.append(item)
        return unique_candidates

    @staticmethod
    def _truncate_text(text: str, limit: int = 500) -> str:
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit] + "...(已截断)"

    @staticmethod
    def _is_valid_cf_clearance(value: str) -> bool:
        if not value:
            return False
        normalized = value.strip()
        if len(normalized) < 10:
            return False
        if " " in normalized or ";" in normalized:
            return False
        return True

    @classmethod
    def _extract_cf_clearance(cls, response_data: Dict[str, Any]) -> Optional[str]:
        solution = response_data.get("solution")
        if not isinstance(solution, dict):
            return None

        cookies = solution.get("cookies")
        if not isinstance(cookies, list):
            return None

        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            if cookie.get("name") != "cf_clearance":
                continue
            value = str(cookie.get("value", "")).strip()
            if cls._is_valid_cf_clearance(value):
                return value

        return None

    async def _request_cf_clearance_once(self, endpoint: str) -> Dict[str, Any]:
        payload = {
            "cmd": "request.get",
            "url": self.TARGET_URL,
            "maxTimeout": self.DEFAULT_MAX_TIMEOUT_MS,
            "userAgent": self.USER_AGENT,
        }

        client = AsyncSession(timeout=90)
        try:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"请求 FlareSolverr 失败: {type(e).__name__}: {str(e)}",
            }
        finally:
            await client.close()

        if response.status_code != 200:
            body = self._truncate_text(response.text or "")
            return {
                "success": False,
                "error": f"FlareSolverr HTTP 状态异常: {response.status_code}",
                "body": body,
                "endpoint": endpoint,
            }

        try:
            data = response.json()
        except Exception:
            return {
                "success": False,
                "error": "FlareSolverr 返回非 JSON 响应",
                "body": self._truncate_text(response.text or ""),
            }

        if data.get("status") != "ok":
            return {
                "success": False,
                "error": f"FlareSolverr 返回失败状态: {data.get('message') or data.get('status') or 'unknown'}",
                "response": self._truncate_text(str(data)),
                "endpoint": endpoint,
            }

        cf_clearance = self._extract_cf_clearance(data)
        if not cf_clearance:
            return {
                "success": False,
                "error": "未从 FlareSolverr 响应中提取到有效 cf_clearance",
                "response": self._truncate_text(str(data)),
                "endpoint": endpoint,
            }

        return {
            "success": True,
            "cf_clearance": cf_clearance,
            "endpoint": endpoint,
        }

    async def _request_cf_clearance(self, endpoint_candidates: list[str]) -> Dict[str, Any]:
        if not endpoint_candidates:
            return {
                "success": False,
                "error": "未提供可用的 FlareSolverr 地址",
            }

        last_error: Optional[Dict[str, Any]] = None
        for endpoint in endpoint_candidates:
            result = await self._request_cf_clearance_once(endpoint)
            if result.get("success"):
                return result

            last_error = result
            # 404 常见于 /v1 与 /v1.request 版本差异，继续尝试候选端点
            error_text = str(result.get("error", ""))
            if "HTTP 状态异常: 404" in error_text:
                logger.warning(f"FlareSolverr 端点不可用，尝试下一个候选端点: {endpoint}")
                continue

            # 非 404 也继续尝试其他候选，避免单点路径差异/代理偶发失败
            logger.warning(f"FlareSolverr 请求失败，尝试下一个候选端点: {endpoint}, error={error_text}")

        return last_error or {
            "success": False,
            "error": "所有 FlareSolverr 端点尝试失败",
        }

    async def _record_runtime_status(
        self,
        *,
        status: str,
        reason: str,
        error: str = "",
        success_at: str = "",
    ):
        try:
            async with AsyncSessionLocal() as db_session:
                await settings_service.set_flaresolverr_runtime_status(
                    db_session,
                    status=status,
                    trigger_reason=reason,
                    attempt_at=self._now_iso(),
                    error=error,
                    success_at=success_at,
                )
        except Exception as e:
            logger.warning(f"记录 FlareSolverr 运行状态失败: {e}")

    async def _refresh_once(self, reason: str, force: bool = False) -> Dict[str, Any]:
        async with AsyncSessionLocal() as db_session:
            config = await settings_service.get_flaresolverr_config(db_session)

        if not config.get("enabled") and not force:
            return {
                "success": False,
                "source": "flaresolverr",
                "skipped": True,
                "error": "FlareSolverr 未启用",
            }

        raw_url = str(config.get("url") or "").strip()
        if not raw_url:
            await self._record_runtime_status(
                status="failed",
                reason=reason,
                error="FlareSolverr 地址为空",
            )
            return {
                "success": False,
                "source": "flaresolverr",
                "skipped": False,
                "error": "FlareSolverr 地址为空",
            }

        endpoint_candidates = self._build_endpoint_candidates(raw_url)
        logger.info(
            f"开始通过 FlareSolverr 刷新 cf_clearance, reason={reason}, endpoints={endpoint_candidates}"
        )

        request_result = await self._request_cf_clearance(endpoint_candidates)
        if not request_result.get("success"):
            await self._record_runtime_status(
                status="failed",
                reason=reason,
                error=str(request_result.get("error") or "FlareSolverr 请求失败"),
            )
            request_result["source"] = "flaresolverr"
            request_result["skipped"] = False
            logger.warning(f"FlareSolverr 刷新失败: {request_result.get('error')}")
            return request_result

        cf_clearance = request_result["cf_clearance"]
        async with AsyncSessionLocal() as db_session:
            saved = await settings_service.set_cf_clearance(db_session, cf_clearance)

        if not saved:
            await self._record_runtime_status(
                status="failed",
                reason=reason,
                error="cf_clearance 获取成功，但写入数据库失败",
            )
            return {
                "success": False,
                "source": "flaresolverr",
                "skipped": False,
                "error": "cf_clearance 获取成功，但写入数据库失败",
            }

        try:
            from app.services.chatgpt import chatgpt_service

            await chatgpt_service.clear_session()
        except Exception as e:
            logger.warning(f"刷新成功后重建 ChatGPT 会话失败: {e}")

        preview = cf_clearance if len(cf_clearance) <= 14 else f"{cf_clearance[:8]}...{cf_clearance[-6:]}"
        await self._record_runtime_status(
            status="success",
            reason=reason,
            success_at=self._now_iso(),
        )
        logger.info("FlareSolverr 刷新 cf_clearance 成功")
        return {
            "success": True,
            "source": "flaresolverr",
            "message": "cf_clearance 已通过 FlareSolverr 刷新并写入",
            "value_preview": preview,
        }

    async def refresh_cf_clearance(self, reason: str = "manual", force: bool = False) -> Dict[str, Any]:
        """
        刷新 cf_clearance；若已有执行中的刷新任务，则等待同一任务结果。
        """
        async with self._lock:
            if self._running_task and not self._running_task.done():
                task = self._running_task
            else:
                task = asyncio.create_task(self._refresh_once(reason, force=force))
                self._running_task = task

        try:
            return await task
        finally:
            async with self._lock:
                if self._running_task is task and task.done():
                    self._running_task = None

    async def _refresh_loop(self):
        logger.info("FlareSolverr 自动刷新任务已启动")
        try:
            while True:
                try:
                    async with AsyncSessionLocal() as db_session:
                        config = await settings_service.get_flaresolverr_config(db_session)

                    if not config.get("enabled"):
                        await asyncio.sleep(self.IDLE_CHECK_SECONDS)
                        continue

                    interval_minutes = int(
                        config.get("refresh_interval_minutes") or DEFAULT_CF_REFRESH_INTERVAL_MINUTES
                    )
                    interval_seconds = max(60, interval_minutes * 60)

                    result = await self.refresh_cf_clearance(reason="scheduled")
                    if result.get("success"):
                        logger.info("定时刷新 cf_clearance 成功")
                    else:
                        logger.warning(f"定时刷新 cf_clearance 失败: {result.get('error')}")

                    await asyncio.sleep(interval_seconds)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"FlareSolverr 自动刷新循环异常: {e}")
                    await self._record_runtime_status(
                        status="failed",
                        reason="scheduled_loop",
                        error=f"自动刷新循环异常: {type(e).__name__}: {str(e)}",
                    )
                    await asyncio.sleep(self.FAILURE_RETRY_SECONDS)
        except asyncio.CancelledError:
            logger.info("FlareSolverr 自动刷新任务收到取消信号")
            raise
        finally:
            logger.info("FlareSolverr 自动刷新任务已停止")

    async def start_refresh_loop(self) -> bool:
        """
        启动后台自动刷新循环。
        Returns:
            是否新启动了任务（False 表示已在运行）
        """
        if self._loop_task and not self._loop_task.done():
            return False

        self._loop_task = asyncio.create_task(self._refresh_loop())
        return True

    async def stop_refresh_loop(self):
        """停止后台自动刷新循环。"""
        task = self._loop_task
        if not task:
            return

        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"停止 FlareSolverr 自动刷新任务时出现异常: {e}")

        self._loop_task = None

    def trigger_refresh_in_background(self, reason: str = "cloudflare_challenge") -> bool:
        """
        触发一次后台刷新，不阻塞当前请求链路。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("当前无可用事件循环，无法触发后台刷新")
            return False

        loop.create_task(self.refresh_cf_clearance(reason=reason))
        return True


flaresolverr_service = FlareSolverrService()
