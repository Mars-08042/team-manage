"""
API 路由
处理 AJAX 请求的 API 端点
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.database import get_db
from app.dependencies.auth import get_current_user, require_admin
from app.services.team import TeamService

logger = logging.getLogger(__name__)

# 创建路由器
router = APIRouter(
    prefix="/api",
    tags=["api"]
)

# 服务实例
team_service = TeamService()


class CFClearanceUpdateRequest(BaseModel):
    """Cloudflare Cookie 更新请求"""
    value: str = Field(..., description="cf_clearance cookie 值")


@router.get("/teams/{team_id}/refresh")
async def refresh_team(
    team_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    刷新 Team 信息

    Args:
        team_id: Team ID
        db: 数据库会话
        current_user: 当前用户（需要登录）

    Returns:
        刷新结果
    """
    try:
        logger.info(f"刷新 Team {team_id} 信息")

        result = await team_service.sync_team_info(team_id, db)

        if not result["success"]:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=result
            )

        return JSONResponse(content=result)

    except Exception as e:
        logger.error(f"刷新 Team 失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": f"刷新 Team 失败: {str(e)}"
            }
        )


@router.get("/settings/cf-clearance")
async def get_cf_clearance_status(
    include_value: bool = Query(False, description="是否返回完整 cf_clearance 值"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    获取 cf_clearance 状态
    """
    try:
        from app.services.settings import settings_service

        status_info = await settings_service.get_cf_clearance_status(db)
        cf_clearance = await settings_service.get_cf_clearance(db)
        value_preview = None
        if cf_clearance:
            if len(cf_clearance) <= 14:
                value_preview = cf_clearance
            else:
                value_preview = f"{cf_clearance[:8]}...{cf_clearance[-6:]}"

        response_data = {
            "success": True,
            "configured": status_info.get("configured", False),
            "updated_at": status_info.get("updated_at"),
            "value_preview": value_preview
        }
        if include_value:
            response_data["value"] = cf_clearance or ""

        return JSONResponse(content=response_data)
    except Exception as e:
        logger.error(f"获取 cf_clearance 状态失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": f"获取 cf_clearance 状态失败: {str(e)}"
            }
        )


@router.put("/settings/cf-clearance")
async def update_cf_clearance(
    payload: CFClearanceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_admin)
):
    """
    手动更新 cf_clearance
    """
    try:
        from app.services.settings import settings_service
        from app.services.chatgpt import chatgpt_service

        value = payload.value.strip()
        if not value:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "success": False,
                    "error": "cf_clearance 不能为空"
                }
            )

        success = await settings_service.set_cf_clearance(db, value)
        if not success:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={
                    "success": False,
                    "error": "保存 cf_clearance 失败"
                }
            )

        # 强制重建会话，确保新 cookie 生效
        await chatgpt_service.clear_session()

        return JSONResponse(
            content={
                "success": True,
                "message": "cf_clearance 已更新并重建会话"
            }
        )
    except Exception as e:
        logger.error(f"更新 cf_clearance 失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": f"更新 cf_clearance 失败: {str(e)}"
            }
        )


@router.post("/settings/cf-clearance/solve")
async def solve_cf_clearance(
    current_user: dict = Depends(require_admin)
):
    """
    手动触发 Cloudflare 过盾脚本
    """
    try:
        from app.services.cloudflare_solver import cloudflare_solver_service

        result = await cloudflare_solver_service.run_solver()
        if result.get("success"):
            return JSONResponse(content=result)

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=result
        )
    except Exception as e:
        logger.error(f"执行过盾脚本失败: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "error": f"执行过盾脚本失败: {str(e)}"
            }
        )
