from __future__ import annotations

import base64
import io
from typing import Any

from src.core.settings import get_settings


class VisionAnalyzer:
    """多模态图片辅助分析入口。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def is_available(self) -> bool:
        return bool(self.settings.multimodal_api_key and self.settings.multimodal_base_url)

    def should_analyze(self, image_payload: Any) -> bool:
        """先过滤明显的纯文字页，减少多模态调用成本。"""

        try:
            import numpy as np
            from PIL import Image
        except ImportError:
            return False

        if not isinstance(image_payload, Image.Image):
            return False

        image_array = np.array(image_payload.convert("RGB"))
        return float(image_array.std()) >= self.settings.vision_color_std_threshold

    def describe(self, image_payload: Any) -> str | None:
        """有配置时走真实多模态调用，没有就跳过。"""

        if not self.is_available:
            return None
        try:
            from openai import OpenAI
            from PIL import Image
        except ImportError:
            return None

        if not isinstance(image_payload, Image.Image):
            return None

        client = OpenAI(
            api_key=self.settings.multimodal_api_key,
            base_url=self.settings.multimodal_base_url,
            timeout=30.0,
        )
        buffer = io.BytesIO()
        image_payload.save(buffer, format="JPEG", quality=85)
        encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")

        response = client.chat.completions.create(
            model=self.settings.multimodal_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "请用中文简要描述这张图片的主要内容、结构和关键信息。"
                                "如果是图表、流程图、表格截图、公章或水印，也请直接点明。"
                                "控制在 200 字内。"
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{encoded}"},
                        },
                    ],
                }
            ],
            max_tokens=200,
        )
        return (response.choices[0].message.content or "").strip() or None
