from __future__ import annotations

import json

from app.config import get_settings
from app.services.ai_service import AIService


def fallback_insight(mapped_preferences: dict) -> str:
    style_profile = mapped_preferences.get("style_profile", {})
    top_styles = [
        style
        for style, _ in sorted(style_profile.items(), key=lambda pair: pair[1], reverse=True)[:2]
    ]
    styles_text = "、".join(top_styles) if top_styles else "简约"
    colors = mapped_preferences.get("color_favorites", [])
    colors_text = "、".join(colors[:3]) if colors else "基础色"
    occasion = mapped_preferences.get("default_occasion", "casual")

    return (
        f"你整体偏向{styles_text}风格，建议以{colors_text}作为主色调，"
        f"并围绕{occasion}场景构建稳定穿搭；在保持舒适度的同时，"
        "每次加入一个小亮点会更有个人辨识度。"
    )


class StyleQuizInsightService:
    def __init__(self, ai_service: AIService | None = None):
        self.settings = get_settings()
        self.ai_service = ai_service or AIService()

    async def generate(self, mapped_preferences: dict) -> str:
        # Keep local/dev runs deterministic and fast.
        if self.settings.debug:
            raise RuntimeError("AI insight disabled in debug mode")

        prompt = (
            "请根据以下穿衣偏好，输出 60-120 字中文风格画像。"
            "要求：1) 口吻自然；2) 不要分点；3) 给出可执行建议。"
            f"\n偏好数据: {json.dumps(mapped_preferences, ensure_ascii=False)}"
        )
        result = await self.ai_service.generate_text(prompt)
        text = str(result).strip()
        if not text:
            raise RuntimeError("empty style insight")
        return text
