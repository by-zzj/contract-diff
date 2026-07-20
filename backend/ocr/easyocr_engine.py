"""
EasyOCR 引擎 — 基于 PyTorch 的中英文 OCR。

特性:
    - 中文识别准确率 ~95%（合同印刷体场景）
    - 纯 Python 安装: pip install easyocr
    - 模型首次使用自动下载，后续缓存
    - 支持手机拍摄、扫描仪、PDF 渲染图片

安装:
    pip install easyocr
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EasyOCRResult:
    text: str
    confidence: float
    blocks: list = field(default_factory=list)
    page_index: int = 0
    quality: Optional[object] = None


class EasyOCREngine:
    """
    EasyOCR 引擎 — 当前主力 OCR 方案。

    pip install easyocr 即可使用，无需额外安装程序。
    支持中英双语，适合合同文档 OCR 场景。
    """

    _instance: Optional["EasyOCREngine"] = None
    _reader = None

    @classmethod
    def get_instance(cls) -> "EasyOCREngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if EasyOCREngine._reader is None:
            self._init_reader()

    def _init_reader(self):
        logger.info("正在加载 EasyOCR 模型...")
        try:
            import easyocr
            EasyOCREngine._reader = easyocr.Reader(
                ['ch_sim', 'en'],
                gpu=False,
                verbose=False,
            )
            logger.info("EasyOCR 模型加载完成")
        except ImportError:
            raise RuntimeError(
                "EasyOCR 未安装。请运行: pip install easyocr"
            )

    def recognize(
        self,
        *,
        image_path: Optional[str] = None,
        image_array: Optional[np.ndarray] = None,
        page_index: int = 0,
        dpi: int = 150,
    ) -> EasyOCRResult:
        if image_path is not None:
            import cv2
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"无法读取图片: {image_path}")
            # EasyOCR 内部会做预处理，直接传 BGR 即可
            results = self._reader.readtext(img, detail=1, paragraph=False)
        elif image_array is not None:
            results = self._reader.readtext(image_array, detail=1, paragraph=False)
        else:
            raise ValueError("必须提供 image_path 或 image_array")

        blocks = []
        all_text_parts = []
        total_conf = 0.0

        for item in results:
            bbox = item[0]
            text = item[1]
            conf = item[2]

            y_center = (bbox[0][1] + bbox[2][1]) / 2 if len(bbox) >= 4 else 0
            blocks.append({
                'text': text,
                'confidence': conf,
                'bbox': bbox,
                'y_center': y_center,
            })
            all_text_parts.append(text)
            total_conf += conf

        # 按 y 坐标排序
        blocks.sort(key=lambda b: (round(b['y_center'] / 30) * 30, b['bbox'][0][0] if b['bbox'] else 0))

        sorted_texts = [b['text'] for b in blocks]
        avg_conf = total_conf / len(blocks) if blocks else 0.0

        return EasyOCRResult(
            text='\n'.join(sorted_texts),
            confidence=round(avg_conf, 3),
            blocks=blocks,
            page_index=page_index,
        )

    def recognize_batch(self, images, dpi=150, on_progress=None):
        results = []
        total = len(images)
        for i, img in enumerate(images):
            if on_progress:
                on_progress(i + 1, total)
            if isinstance(img, (str, Path)):
                result = self.recognize(image_path=str(img), page_index=i, dpi=dpi)
            else:
                result = self.recognize(image_array=img, page_index=i, dpi=dpi)
            results.append(result)
        return results

    @property
    def is_ready(self):
        return EasyOCREngine._reader is not None
