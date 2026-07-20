"""
图像预处理管线 — 提升 OCR 识别准确率。

处理流程:
    原始图片 → 质量评估 → 灰度化 → 对比度增强
    → 自适应二值化 → 去噪 → 纠偏 → 输出

依赖:
    - numpy (必需): 数组运算
    - cv2 (可选): OpenCV 高级预处理。不可用时退化为 PIL 基本处理
    - Pillow (可选): 图片 I/O 和基本调整
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# ── 检查 cv2 可用性 ──────────────────────────────────────

_CV2_AVAILABLE = False
try:
    import cv2
    _CV2_AVAILABLE = True
    logger.info("OpenCV (cv2) 已加载，启用高级预处理")
except ImportError:
    logger.warning("OpenCV (cv2) 不可用，使用 PIL 降级预处理。"
                   "安装 opencv-python-headless 可获得更好的预处理效果。")


@dataclass
class ImageQuality:
    """图像质量评估结果。"""
    width: int
    height: int
    dpi: int
    brightness: float        # 0-255 平均亮度
    contrast: float          # 标准差
    skew_angle: float        # 倾斜角度 (度)
    is_low_quality: bool     # 是否低质量


def assess_quality(image: np.ndarray, dpi: int = 150) -> ImageQuality:
    """
    评估输入图片质量，决定是否需要增强处理。
    """
    h, w = image.shape[:2]

    if _CV2_AVAILABLE:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        skew_angle = _detect_skew_cv2(gray)
    else:
        # PIL fallback
        if len(image.shape) == 3:
            gray = np.mean(image, axis=2)
        else:
            gray = image
        brightness = float(np.mean(gray))
        contrast = float(np.std(gray))
        skew_angle = 0.0

    is_low = (
        dpi < 150
        or contrast < 30
        or abs(skew_angle) > 2.0
    )

    return ImageQuality(
        width=w, height=h, dpi=dpi,
        brightness=brightness, contrast=contrast,
        skew_angle=skew_angle, is_low_quality=is_low,
    )


def enhance(
    image: np.ndarray,
    dpi: int = 150,
    enable_deskew: bool = True,
) -> np.ndarray:
    """
    图像增强主入口 — 对所有输入图片执行标准化预处理。

    有 OpenCV 时：灰度 → CLAHE → 自适应二值化 → 去噪 → 纠偏
    无 OpenCV 时：灰度 → 简单对比度拉伸（PIL 方式）
    """
    if _CV2_AVAILABLE:
        return _enhance_cv2(image, dpi, enable_deskew)
    else:
        return _enhance_pil(image)


def resize_if_needed(image: np.ndarray, max_dim: int = 2048) -> np.ndarray:
    """如果图片尺寸过大，等比缩放。"""
    h, w = image.shape[:2]
    if max(h, w) <= max_dim:
        return image

    scale = max_dim / max(h, w)
    new_w = int(w * scale)
    new_h = int(h * scale)

    if _CV2_AVAILABLE:
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        from PIL import Image
        img = Image.fromarray(image)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        return np.array(img)


def super_resolve(image: np.ndarray, scale: int = 2) -> np.ndarray:
    """超分放大。仅 OpenCV 模式可用，否则直接返回原图。"""
    if not _CV2_AVAILABLE:
        logger.warning("超分需要 OpenCV，跳过")
        return image
    try:
        sr = cv2.dnn_superres.DnnSuperResImpl_create()
        model_path = cv2.dnn_superres.DnnSuperResImpl_getAvailable()
        sr.readModel(model_path)
        sr.setModel("lapsrn", scale)
        return sr.upsample(image)
    except Exception as e:
        logger.warning(f"超分失败: {e}")
        return image


# ── OpenCV 增强管线 ──────────────────────────────────────

def _enhance_cv2(image: np.ndarray, dpi: int, enable_deskew: bool) -> np.ndarray:
    """OpenCV 完整预处理管线。"""
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # CLAHE 对比度增强
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # 自适应二值化
    binary = cv2.adaptiveThreshold(
        enhanced, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=15,
        C=8,
    )

    # 形态学去噪
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    denoised = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)
    denoised = cv2.medianBlur(denoised, 3)

    # 透视纠偏
    if enable_deskew:
        angle = _detect_skew_cv2(denoised)
        if abs(angle) > 0.5:
            denoised = _rotate_cv2(denoised, angle)

    return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)


# ── PIL 降级增强 ─────────────────────────────────────────

def _enhance_pil(image: np.ndarray) -> np.ndarray:
    """Pillow 基本增强（无 OpenCV 时的降级方案）。"""
    try:
        from PIL import Image, ImageFilter, ImageEnhance

        if len(image.shape) == 3:
            pil_img = Image.fromarray(image)
        else:
            pil_img = Image.fromarray(image, mode='L')

        # 转灰度
        if pil_img.mode != 'L':
            pil_img = pil_img.convert('L')

        # 对比度增强
        enhancer = ImageEnhance.Contrast(pil_img)
        pil_img = enhancer.enhance(1.5)

        # 锐化
        pil_img = pil_img.filter(ImageFilter.SHARPEN)

        # 转回 numpy (BGR)
        result = np.array(pil_img)
        if len(result.shape) == 2:
            # 灰度 → BGR
            result = np.stack([result] * 3, axis=-1)

        return result
    except ImportError:
        logger.warning("Pillow 也不可用，跳过预处理")
        return image


# ── OpenCV 辅助 ──────────────────────────────────────────

def _detect_skew_cv2(gray: np.ndarray) -> float:
    """OpenCV 霍夫线检测倾斜角度。"""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)

    if lines is None:
        return 0.0

    angles = []
    for line in lines:
        rho, theta = line[0]
        angle = np.degrees(theta) - 90
        if -45 < angle < 45:
            angles.append(angle)

    if not angles:
        return 0.0

    return float(np.median(angles))


def _rotate_cv2(image: np.ndarray, angle: float) -> np.ndarray:
    """OpenCV 旋转图像。"""
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)

    cos = abs(matrix[0, 0])
    sin = abs(matrix[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)

    matrix[0, 2] += new_w / 2 - center[0]
    matrix[1, 2] += new_h / 2 - center[1]

    rotated = cv2.warpAffine(
        image, matrix, (new_w, new_h),
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )
    return rotated
