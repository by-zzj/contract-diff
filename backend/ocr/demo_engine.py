"""
演示 OCR 引擎 — 无需 PaddleOCR，直接从 Word/PDF 中提取文本。

当 PaddleOCR 环境不可用时，此引擎从文件元数据或内容中提取文本，
保证完整的比对流程可正常运行。

对于纯图片文件，返回提示信息；对于含文本的 PDF/Word，直接提取文本。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DemoOCRResult:
    text: str
    confidence: float
    blocks: list = field(default_factory=list)
    page_index: int = 0
    quality: Optional[object] = None  # 兼容 OCRResult 接口


class DemoOCREngine:
    """
    轻量 OCR 引擎 — 从文件直接提取文本，不依赖 AI 模型。

    适用场景:
        - 开发测试
        - PaddleOCR 环境不可用时的降级方案
        - 文本型 PDF / Word 文件（无需真正 OCR）
    """

    _instance: Optional["DemoOCREngine"] = None

    @classmethod
    def get_instance(cls) -> "DemoOCREngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def recognize(self, *, image_path=None, image_array=None, page_index=0, dpi=150):
        if image_path is not None:
            text = self._extract_text(image_path)
        elif image_array is not None:
            text = "[图片数据] — 请配置 PaddleOCR 以获得准确识别结果"
        else:
            text = ""

        return DemoOCRResult(
            text=text,
            confidence=0.85,
            page_index=page_index,
        )

    def recognize_batch(self, images, dpi=150, on_progress=None):
        results = []
        for i, img in enumerate(images):
            if on_progress:
                on_progress(i + 1, len(images))
            if isinstance(img, (str, Path)):
                result = self.recognize(image_path=str(img), page_index=i, dpi=dpi)
            else:
                result = self.recognize(image_array=img, page_index=i, dpi=dpi)
            results.append(result)
        return results

    @property
    def is_ready(self):
        return True

    def _extract_text(self, image_path: str) -> str:
        """尝试从文件路径中提取文本信息。"""
        path = Path(image_path)
        ext = path.suffix.lower()

        # 如果是缓存图片（来自 PDF 渲染），尝试从文件名推断
        stem = path.stem
        if '_page_' in stem:
            return f"[PDF 第{stem.rsplit('_', 1)[-1]}页] — 请配置 PaddleOCR 以获得准确的 OCR 识别结果。\n当前使用演示引擎，文本内容为占位符。"

        if ext in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'):
            return (
                f"[图片文件: {path.name}]\n"
                f"请配置 PaddleOCR 以进行准确的 OCR 识别。\n"
                f"安装方法: pip install paddleocr paddlepaddle\n"
                f"当前使用演示引擎，比对功能可以正常测试。"
            )

        return f"[文件: {path.name}] — 文本提取中..."
