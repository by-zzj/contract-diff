"""PDF 解析器 — 逐页渲染为图片或提取文本。"""

import logging
from pathlib import Path
from .base import BaseParser, ParsedPage

logger = logging.getLogger(__name__)


class PDFParser(BaseParser):
    """
    PDF 解析器。

    策略（按优先级降级）:
        1. PyMuPDF (fitz): 最佳 — 文本提取 + 高 DPI 渲染
        2. pypdfium2: 备选 — 高性能渲染
        3. pypdf: 降级 — 仅文本提取（扫描件无法处理）
    """

    def __init__(self, dpi: int = 300, text_threshold: int = 50):
        self.dpi = dpi
        self.text_threshold = text_threshold

    def parse(self, file_path: str) -> list[ParsedPage]:
        # 尝试 PyMuPDF
        try:
            return self._parse_with_fitz(file_path)
        except ImportError:
            logger.info("PyMuPDF 不可用，尝试 pypdfium2...")
        except Exception as e:
            logger.warning(f"PyMuPDF 解析失败 ({e})，尝试降级...")

        # 尝试 pypdfium2 (paddleocr 自带)
        try:
            return self._parse_with_pypdfium2(file_path)
        except ImportError:
            logger.info("pypdfium2 不可用，尝试 pypdf...")
        except Exception as e:
            logger.warning(f"pypdfium2 解析失败 ({e})，尝试降级...")

        # 降级到纯文本提取
        return self._parse_with_pypdf(file_path)

    def _parse_with_fitz(self, file_path: str) -> list[ParsedPage]:
        """PyMuPDF 解析（最优方案）。"""
        import fitz
        doc = fitz.open(file_path)
        pages = []

        for i in range(len(doc)):
            page = doc[i]
            text = page.get_text().strip()
            char_count = len(text.replace('\n', '').replace(' ', ''))

            if char_count >= self.text_threshold:
                pages.append(ParsedPage(
                    page_index=i, source_file=file_path, raw_text=text,
                ))
            else:
                mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img_path = self._save_image(file_path, i, pix.samples, pix.width, pix.height)
                pages.append(ParsedPage(
                    page_index=i, source_file=file_path, image_path=img_path,
                ))

        doc.close()
        logger.info(f"PDF (fitz) 解析完成: {file_path}, {len(pages)} 页")
        return pages

    def _parse_with_pypdfium2(self, file_path: str) -> list[ParsedPage]:
        """pypdfium2 渲染解析。"""
        import pypdfium2 as pdfium
        from PIL import Image

        doc = pdfium.PdfDocument(file_path)
        pages = []
        n_pages = len(doc)

        for i in range(n_pages):
            page = doc[i]
            # 渲染为位图
            bitmap = page.render(scale=self.dpi / 72)
            pil_img = bitmap.to_pil()
            img_path = self._save_pil_image(file_path, i, pil_img)
            pages.append(ParsedPage(
                page_index=i, source_file=file_path, image_path=img_path,
            ))

        doc.close()
        logger.info(f"PDF (pypdfium2) 解析完成: {file_path}, {len(pages)} 页")
        return pages

    def _parse_with_pypdf(self, file_path: str) -> list[ParsedPage]:
        """pypdf 纯文本提取（最终降级）。"""
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        pages = []

        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(ParsedPage(
                    page_index=i, source_file=file_path, raw_text=text,
                ))
            else:
                logger.warning(f"PDF 第 {i} 页无文本，且无可用的渲染引擎")

        logger.info(f"PDF (pypdf) 解析完成: {file_path}, {len(pages)} 页（纯文本）")
        return pages

    # ── helpers ──────────────────────────────────────────

    def _save_image(self, file_path: str, page_idx: int,
                    samples, width: int, height: int) -> str:
        """保存原始像素数据为 PNG。"""
        from PIL import Image
        output_dir = Path(file_path).parent / ".contract_diff_cache"
        output_dir.mkdir(exist_ok=True)
        img_path = str(output_dir / f"{Path(file_path).stem}_p{page_idx}.png")
        img = Image.frombytes("RGB", (width, height), samples)
        img.save(img_path, "PNG")
        return img_path

    def _save_pil_image(self, file_path: str, page_idx: int, pil_img) -> str:
        """保存 PIL Image 为 PNG。"""
        output_dir = Path(file_path).parent / ".contract_diff_cache"
        output_dir.mkdir(exist_ok=True)
        img_path = str(output_dir / f"{Path(file_path).stem}_p{page_idx}.png")
        pil_img.save(img_path, "PNG")
        return img_path
