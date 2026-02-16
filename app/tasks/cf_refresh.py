"""
cf_clearance 自动刷新任务
负责在应用生命周期内启动/停止 FlareSolverr 后台刷新循环。
"""
import logging

from app.services.flaresolverr import flaresolverr_service

logger = logging.getLogger(__name__)


async def start_cf_refresh_task():
    """启动 cf_clearance 自动刷新任务。"""
    started = await flaresolverr_service.start_refresh_loop()
    if started:
        logger.info("cf_clearance 自动刷新任务已注册")
    else:
        logger.info("cf_clearance 自动刷新任务已在运行，跳过重复注册")


async def stop_cf_refresh_task():
    """停止 cf_clearance 自动刷新任务。"""
    await flaresolverr_service.stop_refresh_loop()
    logger.info("cf_clearance 自动刷新任务已停止")
