"""BaseEngine - 引擎抽象基类

所有解析引擎（MinerU、PaddleOCR 等）必须继承此接口，
确保上层调度代码与具体引擎实现解耦。
"""

from __future__ import annotations  # 支持 PEP 604 的类型注解语法（str | Path）
from abc import ABC, abstractmethod  # 抽象基类与抽象方法装饰器
from PIL import Image  # Python 图像处理标准库


class BaseEngine(ABC):
    """解析引擎抽象基类。定义所有引擎必须实现的方法。"""

    @abstractmethod
    def initialize(self) -> None:
        """初始化引擎，例如加载模型权重、建立网络连接等。
        首次调用 process_page 前自动执行，支持延迟初始化。
        """
        ...

    @abstractmethod
    def process_page(self, image: Image.Image, page_no: int) -> str:
        """解析单页图片，返回 Markdown 或纯文本。
        
        Args:
            image: PIL Image 对象，页面渲染后的图像。
            page_no: 页码（从 1 开始），仅用于日志记录。
        
        Returns:
            解析结果的 Markdown 字符串，失败返回空字符串。
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称标识，用于日志和状态记录。"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查引擎是否可用（依赖的第三方库是否已安装）。
        如果不可用，调度层应跳过该引擎。
        """
        ...

    def cleanup(self) -> None:
        """释放引擎占用的资源（GPU 显存、模型实例等）。
        在 BatchProcessor 处理完所有批次后调用。
        """
        pass
