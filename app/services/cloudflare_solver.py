"""
Cloudflare 过盾脚本执行服务
用于在运行中的项目里按需手动触发 solve_cf.py
"""
import asyncio
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CloudflareSolverService:
    """Cloudflare 过盾脚本执行服务"""

    DEFAULT_TIMEOUT_SECONDS = 45

    def __init__(self):
        self._lock = asyncio.Lock()
        self._running_task: Optional[asyncio.Task] = None

    @staticmethod
    def _truncate_text(text: str, limit: int = 1000) -> str:
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return text[:limit] + "...(已截断)"

    @staticmethod
    def _run_subprocess_blocking(cmd: list[str], cwd: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore"
        )

    async def _run_solver_once(self, timeout_seconds: int) -> Dict[str, Any]:
        project_root = Path(__file__).resolve().parents[2]
        script_path = project_root / "solve_cf.py"

        if not script_path.exists():
            return {
                "success": False,
                "error": f"未找到脚本: {script_path}"
            }

        cmd = [
            sys.executable,
            str(script_path),
            "--timeout",
            str(timeout_seconds),
        ]

        logger.info("开始执行 Cloudflare 过盾脚本")
        start_ts = time.monotonic()

        try:
            completed = await asyncio.to_thread(
                self._run_subprocess_blocking,
                cmd,
                str(project_root)
            )
        except Exception as e:
            logger.error(f"启动过盾脚本失败: {e!r}")
            return {
                "success": False,
                "error": f"启动过盾脚本失败: {type(e).__name__}: {str(e)}"
            }

        duration = round(time.monotonic() - start_ts, 2)
        stdout_text = (completed.stdout or "").strip()
        stderr_text = (completed.stderr or "").strip()

        if stdout_text:
            logger.info(f"过盾脚本输出: {self._truncate_text(stdout_text, 300)}")
        if stderr_text:
            logger.warning(f"过盾脚本错误输出: {self._truncate_text(stderr_text, 300)}")

        if completed.returncode != 0:
            return {
                "success": False,
                "error": "过盾脚本执行失败",
                "return_code": completed.returncode,
                "duration_seconds": duration,
                "stdout": self._truncate_text(stdout_text),
                "stderr": self._truncate_text(stderr_text),
            }

        # 脚本成功后清理现有 HTTP 会话，确保新 cookie 生效
        try:
            from app.services.chatgpt import chatgpt_service
            await chatgpt_service.clear_session()
        except Exception as e:
            logger.warning(f"过盾后清理 ChatGPT 会话失败: {e}")

        return {
            "success": True,
            "message": "过盾脚本执行成功，cf_clearance 已写入并重建会话",
            "duration_seconds": duration,
            "stdout": self._truncate_text(stdout_text),
        }

    async def run_solver(self, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> Dict[str, Any]:
        """
        执行过盾脚本；若已有执行中的任务，则等待同一个任务结果
        """
        async with self._lock:
            if self._running_task and not self._running_task.done():
                task = self._running_task
            else:
                task = asyncio.create_task(self._run_solver_once(timeout_seconds))
                self._running_task = task

        try:
            result = await task
            return result
        finally:
            async with self._lock:
                if self._running_task is task and task.done():
                    self._running_task = None


cloudflare_solver_service = CloudflareSolverService()
