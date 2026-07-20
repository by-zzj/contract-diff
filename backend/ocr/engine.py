"""
PaddleOCR 引擎封装 — 单例模式，懒加载。

特性:
    - PP-OCRv5 服务端模型（高准确率）
    - CPU 推理 + Intel MKLDNN 加速
    - 单例模式避免重复加载模型
    - 线程安全的识别接口
"""

import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import numpy as np

from .preprocess import (
    assess_quality, enhance, resize_if_needed,
    ImageQuality,
)

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """单页 OCR 识别结果。"""
    text: str                         # 完整文本（按阅读顺序拼接）
    confidence: float                 # 平均置信度
    blocks: list = field(default_factory=list)  # [{text, confidence, bbox}]
    quality: Optional[ImageQuality] = None      # 图片质量评估
    page_index: int = 0               # 页码索引


class OCREngine:
    """
    PaddleOCR 引擎单例。

    Usage:
        engine = OCREngine.get_instance()
        result = engine.recognize(image_path="contract_page1.jpg")
        results = engine.recognize_batch(["p1.jpg", "p2.jpg", "p3.jpg"])
    """

    _instance: Optional["OCREngine"] = None
    _ocr = None

    @classmethod
    def get_instance(cls) -> "OCREngine":
        """获取引擎单例（懒加载）。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        if OCREngine._ocr is None:
            self._init_ocr()

    def _init_ocr(self):
        """初始化 PaddleOCR（延迟导入以加快启动）。"""
        logger.info("正在加载 PaddleOCR 模型...")
        try:
            from paddleocr import PaddleOCR
            OCREngine._ocr = PaddleOCR(
                lang='ch',
                use_angle_cls=True,       # 文本方向分类
                use_gpu=False,             # CPU 推理
                show_log=False,
            )
            logger.info("PaddleOCR 模型加载完成 (PP-OCRv4)")
        except ImportError:
            raise RuntimeError(
                "PaddleOCR 未安装。请运行: pip install paddleocr"
            )

    def recognize(
        self,
        *,
        image_path: Optional[str] = None,
        image_array: Optional[np.ndarray] = None,
        page_index: int = 0,
        dpi: int = 150,
    ) -> OCRResult:
        """
        识别单张图片中的文本。

        Args:
            image_path: 图片文件路径（与 image_array 二选一）
            image_array: numpy 图片数组（与 image_path 二选一）
            page_index: 页码索引
            dpi: 图片 DPI

        Returns:
            OCRResult 识别结果
        """
        if image_path is not None:
            import cv2
            img = cv2.imread(image_path)
            if img is None:
                raise ValueError(f"无法读取图片: {image_path}")
        elif image_array is not None:
            img = image_array
        else:
            raise ValueError("必须提供 image_path 或 image_array")

        # 缩放大图
        img = resize_if_needed(img)

        # 质量评估
        quality = assess_quality(img, dpi)

        # 预处理增强
        enhanced = enhance(img, dpi)

        # PaddleOCR 识别
        results = OCREngine._ocr.ocr(np.array(enhanced), cls=True)

        # 提取结构化结果
        blocks = []

        if results and results[0]:
            for line in results[0]:
                bbox = line[0]          # [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
                text = line[1][0]       # 文本
                conf = line[1][1]       # 置信度

                # 按 y 坐标排序（从上到下，从左到右）
                y_center = (bbox[0][1] + bbox[2][1]) / 2
                blocks.append({
                    'text': text,
                    'confidence': conf,
                    'bbox': bbox,
                    'y_center': y_center,
                })

        # 按 y 坐标排序块，然后按 x 坐标（处理多栏）
        blocks.sort(key=lambda b: (round(b['y_center'] / 30) * 30, b['bbox'][0][0]))

        all_text_parts = []
        total_conf = 0.0
        count = 0

        for block in blocks:
            all_text_parts.append(block['text'])
            total_conf += block['confidence']
            count += 1

        avg_conf = total_conf / count if count > 0 else 0.0
        full_text = '\n'.join(all_text_parts)

        return OCRResult(
            text=full_text,
            confidence=avg_conf,
            blocks=blocks,
            quality=quality,
            page_index=page_index,
        )

    def recognize_batch(
        self,
        images: list,
        dpi: int = 150,
        on_progress=None,
    ) -> list[OCRResult]:
        """
        批量识别多张图片。

        Args:
            images: 图片路径列表 或 numpy 数组列表
            dpi: 图片 DPI
            on_progress: 进度回调 (current, total) -> None

        Returns:
            OCRResult 列表
        """
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
    def is_ready(self) -> bool:
        """引擎是否已初始化就绪。"""
        return OCREngine._ocr is not None
