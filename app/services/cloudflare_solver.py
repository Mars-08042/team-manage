"""
Cloudflare 过盾执行服务
仅调用 FlareSolverr 远程刷新。
"""
import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CloudflareSolverService:
    """Cloudflare 过盾执行服务"""

    DEFAULT_TIMEOUT_SECONDS = 45  # 兼容旧接口参数，当前不再使用脚本超时

    def __init__(self):
        self._lock = asyncio.Lock()
        self._running_task: Optional[asyncio.Task] = None

    async def _run_solver_once(self) -> Dict[str, Any]:
        try:
            from app.services.flaresolverr import flaresolverr_service

            result = await flaresolverr_service.refresh_cf_clearance(reason="manual", force=True)
            if result.get("success"):
                return result

            manual_guide = "docs\\cf-clearance-ssh-tunnel-guide.md"
            return {
                "success": False,
                "source": "flaresolverr",
                "error": result.get("error") or "FlareSolverr 刷新失败",
                "manual_guide": manual_guide,
                "manual_guide_message": f"请按 {manual_guide} 手动处理",
            }
        except Exception as e:
            logger.error(f"执行 FlareSolverr 刷新失败: {e}")
            manual_guide = "docs\\cf-clearance-ssh-tunnel-guide.md"
            return {
                "success": False,
                "source": "flaresolverr",
                "error": f"执行 FlareSolverr 刷新失败: {type(e).__name__}: {str(e)}",
                "manual_guide": manual_guide,
                "manual_guide_message": f"请按 {manual_guide} 手动处理",
            }

    async def run_solver(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, Any]:
        """
        手动触发过盾，仅调用 FlareSolverr 方案。
        若已有执行中的任务，则等待同一个任务结果。
        """
        _ = timeout_seconds
        async with self._lock:
            if self._running_task and not self._running_task.done():
                task = self._running_task
            else:
                task = asyncio.create_task(self._run_solver_once())
                self._running_task = task

        try:
            result = await task
            return result
        finally:
            async with self._lock:
                if self._running_task is task and task.done():
                    self._running_task = None


cloudflare_solver_service = CloudflareSolverService()
