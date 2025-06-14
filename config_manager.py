from typing import Any
from astrbot.api import AstrBotConfig


class ConfigManager:
    def __init__(self, config: AstrBotConfig):
        self.config = config
        self.max_text_length = self.config.get("max_text_length", 500)
        self.max_images = self.config.get("max_images", 1)
        self.api_base_url = self.config.get("api_base_url", "")
        self.use_base64 = self.config.get("use_base64", False)
        self.enable_content_safety = self.config.get("enable_content_safety", False)

    def check_content_limits(self, content: str, images: list) -> tuple[bool, str]:
        """检查内容是否符合限制"""
        if len(content) > self.max_text_length:
            return False, f"漂流瓶内容超过长度限制（最大 {self.max_text_length} 字）"

        if len(images) > self.max_images:
            return False, f"图片数量超过限制（最大 {self.max_images} 张）"

        return True, ""
