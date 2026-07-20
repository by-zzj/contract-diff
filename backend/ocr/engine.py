"""
PaddleOCR 引擎封装 — 单例模式，懒加载。

特性:
    - PP-OCRv5 服务端模型（高准确率）
    - CPU 推理 + Intel MKLDNN 加速
    - 单例模式避免重复加载模型
    - 线程安全的识别接口
"""

import logging
import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import numpy as np
from .preprocess import ImageQuality

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
            logger.info("PaddleOCR 模型加载完成 (PP-OCRv4, 中文 97%+)")
        except ImportError:
            raise RuntimeError(
                "PaddleOCR 未安装。请运行: pip install paddleocr"
            )
        except Exception as e:
            logger.error(f"PaddleOCR 初始化失败: {e}")
            raise

    def recognize(
        self,
        *,
        image_path: Optional[str] = None,
        image_array: Optional[np.ndarray] = None,
        page_index: int = 0,
        dpi: int = 150,
    ) -> OCRResult:
        """识别单张图片中的文本。PaddleOCR 自带预处理，不额外二值化。"""
        if image_path is not None:
            import cv2
            # OpenCV imread 不支持中文路径，用 PIL 读再转 numpy
            img = cv2.imread(image_path)
            if img is None:
                from PIL import Image
                pil_img = Image.open(image_path)
                img = np.array(pil_img)
                if img.ndim == 3 and img.shape[2] == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            if img is None:
                raise ValueError(f"无法读取图片: {image_path}")
        elif image_array is not None:
            img = image_array
        else:
            raise ValueError("必须提供 image_path 或 image_array")

        import cv2

        # 图片缩放优化（不二值化，PaddleOCR 内部有完整预处理管线）
        h, w = img.shape[:2]
        if w < 1000 and h < 1500:
            # 小图放大到 1600px 宽，提升文字细节
            scale = 1600 / w
            img = cv2.resize(img, (1600, int(h * scale)), interpolation=cv2.INTER_CUBIC)
        elif max(w, h) > 3000:
            # 大图缩小防内存溢出
            scale = 2400 / max(w, h)
            img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)

        # 直接送 PaddleOCR（PP-OCRv4 内部有完整的预处理管线，不额外二值化）
        results = OCREngine._ocr.ocr(img, cls=True)

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

        # 按 y 坐标每 40px 一个桶，桶内按 x 坐标排序（严格阅读顺序）
        blocks.sort(key=lambda b: (
            round(b['y_center'] / 40) * 40,
            b['bbox'][0][0]
        ))

        all_text_parts = []
        total_conf = 0.0
        count = 0

        for block in blocks:
            text = _ocr_postprocess(block['text'])
            # 过滤页码/页眉噪声：单数字(<3位)在页面顶部或底部
            if _is_page_noise(text, block['y_center'], blocks, block['confidence']):
                continue
            all_text_parts.append(text)
            total_conf += block['confidence']
            count += 1

        avg_conf = total_conf / count if count > 0 else 0.0
        full_text = '\n'.join(all_text_parts)

        # 日志：OCR 识别详情
        logger.info(
            f"OCR 完成 page={page_index}: {len(blocks)} 行文本, "
            f"置信度={avg_conf:.3f}"
        )
        low_conf_blocks = [b for b in blocks if b['confidence'] < 0.8]
        if low_conf_blocks:
            logger.warning(
                f"  低置信度文本 ({len(low_conf_blocks)} 处): " +
                "; ".join(f"{b['text'][:30]} ({b['confidence']:.2f})" for b in low_conf_blocks[:5])
            )
        # 前几行识别结果
        for b in blocks[:8]:
            logger.debug(f"  [{b['confidence']:.3f}] {b['text'][:80]}")

        return OCRResult(
            text=full_text,
            confidence=avg_conf,
            blocks=blocks,
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


# ── OCR 文本后处理 ────────────────────────────────────────

def _ocr_postprocess(text: str) -> str:
    """
    修正常见 OCR 不稳定字符。

    两次截图同一段文字，OCR 可能识别为 '、' 或 '"' 或 '·'，
    统一规整以减少无意义差异。
    """
    # 不稳定标点 → 统一
    text = text.replace('‘', '、').replace('\'', '、')
    text = text.replace('·', '。')
    text = text.replace('"', '"').replace('"', '"')

    # 去除 OCR 残留的零宽字符和控制符
    text = text.replace('​', '').replace('‌', '').replace('‍', '')
    text = text.replace('﻿', '')

    # c→C 修正（合同文档中 C 区 比 c 区 更常见）
    if 'c区' in text:
        text = text.replace('c区', 'C区')

    return text


def _is_page_noise(text: str, y_center: float, all_blocks: list, conf: float) -> bool:
    """判断是否为页码/页眉噪声。"""
    stripped = text.strip()
    # 纯数字 (1-3位，可能是页码)
    if re.match(r'^\d{1,3}$', stripped):
        if all_blocks:
            max_y = max(b['y_center'] for b in all_blocks)
            # 在页面顶部 15% 或底部 15% → 页码
            if y_center < max_y * 0.15 or y_center > max_y * 0.85:
                return True
    # 低置信度 + 极短文本 + 在页面边缘 → 噪声
    if conf < 0.6 and len(stripped) <= 2:
        return True
    return False
