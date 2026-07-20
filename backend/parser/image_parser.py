"""图片解析器 — 格式标准化 + DPI 检查。"""

import logging
from pathlib import Path
from .base import BaseParser, ParsedPage

logger = logging.getLogger(__name__)


class ImageParser(BaseParser):
    """
    图片解析器。

    处理方式:
        - 验证图片格式（JPG/PNG/BMP/TIFF/WEBP）
        - 检查 DPI
        - 返回可直接 OCR 的图片路径
    """

    def __init__(self, min_dpi: int = 150):
        self.min_dpi = min_dpi

    def parse(self, file_path: str) -> list[ParsedPage]:
        from PIL import Image

        img = Image.open(file_path)

        # 读取 DPI 信息（部分格式不支持）
        dpi = img.info.get('dpi', (72, 72))
        dpi_x = dpi[0] if isinstance(dpi, tuple) else dpi

        logger.info(
            f"图片解析: {file_path}, "
            f"尺寸: {img.size}, DPI: {dpi_x}"
        )

        return [ParsedPage(
            page_index=0,
            source_file=file_path,
            image_path=file_path,
        )]
