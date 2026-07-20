"""Word 解析器 — 提取 .docx 文本内容。"""

import logging
from pathlib import Path
from .base import BaseParser, ParsedPage

logger = logging.getLogger(__name__)


class WordParser(BaseParser):
    """
    Word (.docx) 解析器。

    处理方式:
        - 提取段落文本，按段落分行
        - 如有嵌入图片，导出为 PNG
        - 按页面近似划分（每 40 自然段视为一页）
    """

    def __init__(self, paragraphs_per_page: int = 40):
        self.paragraphs_per_page = paragraphs_per_page

    def parse(self, file_path: str) -> list[ParsedPage]:
        try:
            from docx import Document
        except ImportError as e:
            raise ImportError(
                "python-docx 未安装。请运行: pip install python-docx"
            ) from e

        try:
            doc = Document(file_path)
        except Exception as e:
            # .doc（旧格式）无法用 python-docx 打开
            ext = Path(file_path).suffix.lower()
            if ext == '.doc':
                raise ValueError(
                    f"不支持旧版 .doc 格式: {Path(file_path).name}\n"
                    "请用 Word 将文件另存为 .docx 格式后再导入。\n"
                    "(文件 → 另存为 → Word 文档 (*.docx))"
                ) from e
            raise ValueError(
                f"无法打开文件: {Path(file_path).name}\n"
                f"{type(e).__name__}: {e}\n"
                "请确认文件未损坏且格式为 .docx"
            ) from e

        # 提取所有段落文本
        all_paragraphs = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                all_paragraphs.append(text)

        # 按 approximate 页码分组
        pages = []
        chunk_size = self.paragraphs_per_page
        for i in range(0, len(all_paragraphs), chunk_size):
            chunk = all_paragraphs[i:i + chunk_size]
            page_index = i // chunk_size
            pages.append(ParsedPage(
                page_index=page_index,
                source_file=file_path,
                raw_text='\n\n'.join(chunk),
            ))

        # 如果文档为空但有图片，尝试提取图片
        if not pages:
            # 检查是否有嵌入图片
            output_dir = Path(file_path).parent / ".contract_diff_cache"
            output_dir.mkdir(exist_ok=True)

            img_index = 0
            for rel in doc.part.rels.values():
                if "image" in rel.reltype:
                    img_data = rel.target_part.blob
                    ext = Path(rel.target_ref).suffix or '.png'
                    img_path = str(output_dir / f"{Path(file_path).stem}_img{img_index}{ext}")
                    with open(img_path, 'wb') as f:
                        f.write(img_data)
                    pages.append(ParsedPage(
                        page_index=img_index,
                        source_file=file_path,
                        image_path=img_path,
                    ))
                    img_index += 1

        logger.info(f"Word 解析完成: {file_path}, {len(pages)} 页")
        return pages
