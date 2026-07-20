"""
Tesseract OCR 引擎 — 基于 pytesseract 的中英文 OCR。

需要安装 Tesseract OCR 程序:
    https://github.com/UB-Mannheim/tesseract/wiki
    下载 tesseract-ocr-w64-setup-5.5.0.*.exe，安装时勾选 Chinese (Simplified)

Python 依赖:
    pip install pytesseract Pillow
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TesseractOCRResult:
    text: str
    confidence: float
    blocks: list = field(default_factory=list)
    page_index: int = 0
    quality: Optional[object] = None


class TesseractEngine:
    """
    Tesseract OCR 引擎。

    pip install pytesseract + 安装 Tesseract OCR 程序 即可使用。
    支持中英双语识别，适合合同文档场景。
    """

    _instance: Optional["TesseractEngine"] = None

    @classmethod
    def get_instance(cls) -> "TesseractEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        import pytesseract
        # 尝试自动找到 tesseract
        import shutil
        found = shutil.which('tesseract')
        if found:
            pytesseract.pytesseract.tesseract_cmd = found
        logger.info(f"Tesseract: {pytesseract.pytesseract.tesseract_cmd or 'auto-detect'}")

    def recognize(
        self, *, image_path=None, image_array=None, page_index=0, dpi=150
    ):
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = (
            pytesseract.pytesseract.tesseract_cmd or 'tesseract'
        )

        if image_path is not None:
            from PIL import Image
            img = Image.open(image_path)
        elif image_array is not None:
            from PIL import Image
            img = Image.fromarray(image_array)
        else:
            raise ValueError("必须提供 image_path 或 image_array")

        try:
            text = pytesseract.image_to_string(
                img, lang='chi_sim+eng',
                config='--oem 3 --psm 6',
            )
            # 用 image_to_data 获取置信度
            data = pytesseract.image_to_data(
                img, lang='chi_sim+eng',
                output_type=pytesseract.Output.DICT,
            )
            confidences = [
                int(c) for c in data['conf']
                if isinstance(c, (int, float)) and c > 0
            ]
            avg_conf = sum(confidences) / len(confidences) / 100 if confidences else 0.85
        except pytesseract.TesseractNotFoundError:
            raise RuntimeError(
                "Tesseract OCR 程序未安装。\n"
                "请从 https://github.com/UB-Mannheim/tesseract/wiki 下载安装，\n"
                "安装时务必勾选 Chinese (Simplified) 语言包。"
            )
        except pytesseract.TesseractError as e:
            # 中文语言包未安装
            if 'chi_sim' in str(e).lower() or 'Failed loading' in str(e):
                raise RuntimeError(
                    "Tesseract 中文语言包未安装。\n"
                    "请重新运行 Tesseract 安装程序，勾选: Chinese (Simplified)\n"
                    "或手动下载 chi_sim.traineddata 到 tessdata 目录。"
                )
            raise

        return TesseractOCRResult(
            text=text.strip(),
            confidence=round(avg_conf, 3),
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
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False
