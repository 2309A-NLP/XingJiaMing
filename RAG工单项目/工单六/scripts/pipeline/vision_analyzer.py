"""多模态图片解析模块 - 调用 MiMo-V2.5 生成图片语义描述

职责：
  1. 接收 PIL Image 对象
  2. 调用 MiMo-V2.5 多模态 API，生成图片描述
  3. 返回描述文字，用于插入到文档 Markdown 中

使用场景：
  - 文档入库时，对 PDF 中的图片区域生成文字描述
  - 描述和正文一起存入 Milvus，查询时不需要再调用多模态 API
"""
from __future__ import annotations
import base64
import io
import logging
import os
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)

# 图片语义解析的 prompt
VISION_PROMPT = """请用中文详细描述这张图片的内容，包括：
1. 图片类型（照片、图表、流程图、表格截图、公章、水印等）
2. 主要内容和关键信息
3. 如果是图表，描述数据趋势和关键数值
4. 如果是流程图，描述主要步骤和关系

要求：
- 用简洁的语言，不超过200字
- 不要加"这张图片是"之类的开头，直接描述
- 如果是公章/水印/装饰性图片，只说"公章"或"水印"即可"""


class VisionAnalyzer:
    """多模态图片解析器，调用 MiMo-V2.5 生成图片描述。"""

    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        """
        Args:
            api_key: API Key，默认从环境变量 VISION_API_KEY 读取。
            base_url: API 地址，默认从环境变量 VISION_BASE_URL 读取。
            model: 模型名称，默认从环境变量 VISION_MODEL 读取。
        """
        from openai import OpenAI

        self._api_key = api_key or os.getenv('VISION_API_KEY', '')
        self._base_url = base_url or os.getenv('VISION_BASE_URL', '')
        self._model = model or os.getenv('VISION_MODEL', 'mimo-v2.5')

        if not self._api_key:
            logger.warning('VISION_API_KEY 未配置，图片语义解析将跳过')
            self._client = None
            return

        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=30.0,
        )
        logger.info('图片解析器初始化完成: %s @ %s', self._model, self._base_url)

    @property
    def is_available(self) -> bool:
        """检查是否可用"""
        return self._client is not None

    def _image_to_base64(self, image: Image.Image) -> str:
        """PIL Image 转 base64 字符串"""
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    @staticmethod
    def should_analyze(image: Image.Image) -> bool:
        """快速判断页面是否需要多模态解析
        
        规则：
          - 纯文字页面（颜色单一）→ 跳过
          - 有图表/图片（颜色丰富）→ 需要解析
        """
        import numpy as np
        img_array = np.array(image.convert('RGB'))
        
        # 计算颜色丰富度（标准差）
        std = img_array.std()
        
        # 颜色标准差小于30，认为是纯文字页面，跳过
        if std < 30:
            return False
        return True

    def analyze(self, image: Image.Image, page_no: int = 0, force: bool = False) -> Optional[str]:
        """解析图片，返回文字描述。

        Args:
            image: PIL Image 对象。
            page_no: 页码（用于日志）。
            force: 是否强制解析（跳过判断）。

        Returns:
            图片描述文字，失败返回 None。
        """
        if not self.is_available:
            return None
            
        # 快速判断是否需要解析
        if not force and not self.should_analyze(image):
            logger.debug('第%d页: 纯文字页面，跳过图片解析', page_no)
            return None

        try:
            # 图片转 base64
            b64 = self._image_to_base64(image)

            # 调用多模态 API
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{b64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300,
            )

            description = response.choices[0].message.content.strip()
            logger.info('第%d页图片解析完成: %s...', page_no, description[:50])
            return description

        except Exception as e:
            logger.warning('第%d页图片解析失败: %s', page_no, str(e)[:100])
            return None