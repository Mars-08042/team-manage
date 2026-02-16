"""
系统设置服务
管理系统配置的读取、更新和缓存
"""
from typing import Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Setting
import logging

logger = logging.getLogger(__name__)

DEFAULT_CF_REFRESH_INTERVAL_MINUTES = 120
MIN_CF_REFRESH_INTERVAL_MINUTES = 30
MAX_CF_REFRESH_INTERVAL_MINUTES = 1440


class SettingsService:
    """系统设置服务类"""

    def __init__(self):
        self._cache: Dict[str, str] = {}

    async def get_setting(self, session: AsyncSession, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        获取单个配置项

        Args:
            session: 数据库会话
            key: 配置项键名
            default: 默认值

        Returns:
            配置项值,如果不存在则返回默认值
        """
        # 先从缓存获取
        if key in self._cache:
            return self._cache[key]

        # 从数据库获取
        result = await session.execute(
            select(Setting).where(Setting.key == key)
        )
        setting = result.scalar_one_or_none()

        if setting:
            self._cache[key] = setting.value
            return setting.value

        return default

    async def get_all_settings(self, session: AsyncSession) -> Dict[str, str]:
        """
        获取所有配置项

        Args:
            session: 数据库会话

        Returns:
            配置项字典
        """
        result = await session.execute(select(Setting))
        settings = result.scalars().all()

        settings_dict = {s.key: s.value for s in settings}
        self._cache.update(settings_dict)

        return settings_dict

    async def update_setting(self, session: AsyncSession, key: str, value: str) -> bool:
        """
        更新单个配置项

        Args:
            session: 数据库会话
            key: 配置项键名
            value: 配置项值

        Returns:
            是否更新成功
        """
        try:
            result = await session.execute(
                select(Setting).where(Setting.key == key)
            )
            setting = result.scalar_one_or_none()

            if setting:
                setting.value = value
            else:
                setting = Setting(key=key, value=value)
                session.add(setting)

            await session.commit()

            # 更新缓存
            self._cache[key] = value

            logger.info(f"配置项 {key} 已更新")
            return True

        except Exception as e:
            logger.error(f"更新配置项 {key} 失败: {e}")
            await session.rollback()
            return False

    async def update_settings(self, session: AsyncSession, settings: Dict[str, str]) -> bool:
        """
        批量更新配置项

        Args:
            session: 数据库会话
            settings: 配置项字典

        Returns:
            是否更新成功
        """
        try:
            for key, value in settings.items():
                result = await session.execute(
                    select(Setting).where(Setting.key == key)
                )
                setting = result.scalar_one_or_none()

                if setting:
                    setting.value = value
                else:
                    setting = Setting(key=key, value=value)
                    session.add(setting)

            await session.commit()

            # 更新缓存
            self._cache.update(settings)

            logger.info(f"批量更新了 {len(settings)} 个配置项")
            return True

        except Exception as e:
            logger.error(f"批量更新配置项失败: {e}")
            await session.rollback()
            return False

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("配置缓存已清空")

    async def get_proxy_config(self, session: AsyncSession) -> Dict[str, str]:
        """
        获取代理配置

        Returns:
            代理配置字典
        """
        proxy_enabled = await self.get_setting(session, "proxy_enabled", "false")
        proxy = await self.get_setting(session, "proxy", "")

        return {
            "enabled": proxy_enabled.lower() == "true",
            "proxy": proxy
        }

    async def update_proxy_config(
        self,
        session: AsyncSession,
        enabled: bool,
        proxy: str = ""
    ) -> bool:
        """
        更新代理配置

        Args:
            session: 数据库会话
            enabled: 是否启用代理
            proxy: 代理地址 (格式: http://host:port 或 socks5://host:port)

        Returns:
            是否更新成功
        """
        settings = {
            "proxy_enabled": str(enabled).lower(),
            "proxy": proxy
        }

        return await self.update_settings(session, settings)

    async def get_flaresolverr_config(self, session: AsyncSession) -> Dict[str, Any]:
        """
        获取 FlareSolverr 自动刷新配置

        Returns:
            FlareSolverr 配置字典
        """
        enabled_raw = await self.get_setting(session, "flaresolverr_enabled", "false")
        url_raw = await self.get_setting(session, "flaresolverr_url", "")
        interval_raw = await self.get_setting(
            session,
            "cf_clearance_refresh_interval",
            str(DEFAULT_CF_REFRESH_INTERVAL_MINUTES),
        )

        try:
            interval_minutes = int(str(interval_raw).strip() or DEFAULT_CF_REFRESH_INTERVAL_MINUTES)
        except Exception:
            interval_minutes = DEFAULT_CF_REFRESH_INTERVAL_MINUTES

        interval_minutes = max(
            MIN_CF_REFRESH_INTERVAL_MINUTES,
            min(MAX_CF_REFRESH_INTERVAL_MINUTES, interval_minutes),
        )

        return {
            "enabled": str(enabled_raw).lower() == "true",
            "url": (url_raw or "").strip(),
            "refresh_interval_minutes": interval_minutes,
        }

    async def update_flaresolverr_config(
        self,
        session: AsyncSession,
        enabled: bool,
        url: str,
        refresh_interval_minutes: int,
    ) -> bool:
        """
        更新 FlareSolverr 自动刷新配置

        Args:
            session: 数据库会话
            enabled: 是否启用 FlareSolverr 自动刷新
            url: FlareSolverr 服务地址
            refresh_interval_minutes: 刷新间隔（分钟）

        Returns:
            是否更新成功
        """
        normalized_interval = max(
            MIN_CF_REFRESH_INTERVAL_MINUTES,
            min(MAX_CF_REFRESH_INTERVAL_MINUTES, int(refresh_interval_minutes)),
        )

        settings = {
            "flaresolverr_enabled": str(enabled).lower(),
            "flaresolverr_url": (url or "").strip(),
            "cf_clearance_refresh_interval": str(normalized_interval),
        }
        return await self.update_settings(session, settings)

    async def get_flaresolverr_runtime_status(self, session: AsyncSession) -> Dict[str, Optional[str]]:
        """
        获取 FlareSolverr 运行状态（最近一次刷新结果）

        Returns:
            运行状态字典
        """
        last_status = await self.get_setting(session, "flaresolverr_last_status", "idle")
        last_error = await self.get_setting(session, "flaresolverr_last_error", "")
        last_attempt_at = await self.get_setting(session, "flaresolverr_last_attempt_at", "")
        last_success_at = await self.get_setting(session, "flaresolverr_last_success_at", "")
        last_trigger_reason = await self.get_setting(session, "flaresolverr_last_trigger_reason", "")

        return {
            "last_status": (last_status or "idle").strip() or "idle",
            "last_error": (last_error or "").strip() or None,
            "last_attempt_at": (last_attempt_at or "").strip() or None,
            "last_success_at": (last_success_at or "").strip() or None,
            "last_trigger_reason": (last_trigger_reason or "").strip() or None,
        }

    async def set_flaresolverr_runtime_status(
        self,
        session: AsyncSession,
        *,
        status: str,
        trigger_reason: str,
        attempt_at: str,
        error: str = "",
        success_at: str = "",
    ) -> bool:
        """
        更新 FlareSolverr 运行状态（最近一次刷新结果）
        """
        payload = {
            "flaresolverr_last_status": (status or "idle").strip() or "idle",
            "flaresolverr_last_error": (error or "").strip(),
            "flaresolverr_last_attempt_at": (attempt_at or "").strip(),
            "flaresolverr_last_success_at": (success_at or "").strip(),
            "flaresolverr_last_trigger_reason": (trigger_reason or "").strip(),
        }
        return await self.update_settings(session, payload)

    async def get_cf_clearance(self, session: AsyncSession) -> Optional[str]:
        """
        获取 Cloudflare 通行 Cookie

        Args:
            session: 数据库会话

        Returns:
            cf_clearance 值，不存在时返回 None
        """
        value = await self.get_setting(session, "cf_clearance", "")
        if not value:
            return None
        normalized_value = value.strip()
        return normalized_value or None

    async def set_cf_clearance(self, session: AsyncSession, value: str) -> bool:
        """
        保存 Cloudflare 通行 Cookie

        Args:
            session: 数据库会话
            value: cf_clearance 值

        Returns:
            是否保存成功
        """
        normalized_value = (value or "").strip()
        return await self.update_setting(session, "cf_clearance", normalized_value)

    async def get_cf_clearance_status(self, session: AsyncSession) -> Dict[str, Any]:
        """
        获取 cf_clearance 配置状态

        Args:
            session: 数据库会话

        Returns:
            配置状态字典
        """
        result = await session.execute(
            select(Setting).where(Setting.key == "cf_clearance")
        )
        setting = result.scalar_one_or_none()

        if setting and setting.value:
            self._cache["cf_clearance"] = setting.value

        configured = bool(setting and setting.value and setting.value.strip())
        updated_at = setting.updated_at.isoformat() if setting and setting.updated_at else None

        return {
            "configured": configured,
            "updated_at": updated_at
        }

    async def get_log_level(self, session: AsyncSession) -> str:
        """
        获取日志级别

        Returns:
            日志级别
        """
        return await self.get_setting(session, "log_level", "INFO")

    async def update_log_level(self, session: AsyncSession, level: str) -> bool:
        """
        更新日志级别

        Args:
            session: 数据库会话
            level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)

        Returns:
            是否更新成功
        """
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if level.upper() not in valid_levels:
            logger.error(f"无效的日志级别: {level}")
            return False

        success = await self.update_setting(session, "log_level", level.upper())

        if success:
            # 动态更新日志级别
            logging.getLogger().setLevel(level.upper())
            logger.info(f"日志级别已更新为: {level.upper()}")

        return success


# 创建全局实例
settings_service = SettingsService()
