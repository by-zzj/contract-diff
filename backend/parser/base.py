"""
文档解析器 — 将不同格式的输入统一转为图片列表。

支持的输入格式:
    - PDF: 逐页渲染为 300 DPI PNG
    - Word (.docx): 提取文本 + 嵌入图片
    - 图片: 格式标准化 + DPI 检查
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ParsedPage:
    """统一解析结果 — 单页内容。"""
    page_index: int
    source_file: str           # 来源文件路径
    image_path: Optional[str] = None   # 渲染图片路径（扫描型）
    raw_text: Optional[str] = None     # 直接提取的文本（文字型 PDF/Word）


class BaseParser(ABC):
    """解析器抽象接口。"""

    @abstractmethod
    def parse(self, file_path: str) -> list[ParsedPage]:
        """
        解析文件，返回统一的 ParsedPage 列表。

        Args:
            file_path: 文件路径

        Returns:
            ParsedPage 列表
        """
        ...

    @staticmethod
    def get_parser(file_path: str) -> "BaseParser":
        """
        根据文件扩展名自动选择合适的解析器。
        """
        ext = Path(file_path).suffix.lower()
        if ext == '.pdf':
            from .pdf_parser import PDFParser
            return PDFParser()
        elif ext in ('.docx', '.doc'):
            from .word_parser import WordParser
            return WordParser()
        elif ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'):
            from .image_parser import ImageParser
            return ImageParser()
        else:
            raise ValueError(f"不支持的文件格式: {ext}")
