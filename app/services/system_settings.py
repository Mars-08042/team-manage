import json
import os
import aiofiles
from typing import Any, Dict

SETTINGS_FILE = "data/settings.json"

class SystemSettingsService:
    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists("data"):
            os.makedirs("data")
        if not os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

    async def _load_settings(self):
        if not self._cache:
            try:
                async with aiofiles.open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    content = await f.read()
                    self._cache = json.loads(content) if content else {}
            except Exception as e:
                print(f"Error loading settings: {e}")
                self._cache = {}

    async def get_setting(self, key: str, default: Any = None) -> Any:
        await self._load_settings()
        return self._cache.get(key, default)

    async def set_setting(self, key: str, value: Any):
        await self._load_settings()
        self._cache[key] = value
        async with aiofiles.open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            await f.write(json.dumps(self._cache, indent=2, ensure_ascii=False))

system_settings_service = SystemSettingsService()
