"""
逐句差异比对 — 对已对齐的段落做字符级差异分析。

使用 jieba 分词 + difflib.SequenceMatcher，输出差异片段列表。
"""

import logging
import uuid
from difflib import SequenceMatcher
from typing import List, Optional
from dataclasses import dataclass, field

from .normalizer import normalize
from .aligner import AlignmentResult, AlignedPair

logger = logging.getLogger(__name__)


@dataclass
class DiffFragment:
    """单个差异片段 — 包含字符级偏移量供前端精确高亮。"""
    type: str                     # 'replace' | 'delete' | 'insert'
    original: str                 # 原件文本（delete/replace 时有值）
    compared: str                 # 比对件文本（insert/replace 时有值）
    original_start: int = 0       # 原件段落中的字符偏移
    original_end: int = 0
    compared_start: int = 0       # 比对件段落中的字符偏移
    compared_end: int = 0


@dataclass
class DiffRecord:
    """单条差异记录（前端渲染用）。"""
    id: str
    page_label: str                    # 页码标注
    paragraph_index: int               # 段落序号
    type: str                          # 'added' | 'deleted' | 'modified'
    original_text: str                 # 原件完整文本
    compared_text: str                 # 比对件完整文本
    confidence: float                  # OCR 置信度
    fragments: List[DiffFragment] = field(default_factory=list)
    summary: str = ""                  # 差异摘要


def compare(
    original_text: str,
    compared_text: str,
    alignment: Optional[AlignmentResult] = None,
    page_label: str = "",
    base_confidence: float = 0.95,
) -> List[DiffRecord]:
    """
    主比对入口。

    Args:
        original_text: 原件完整文本
        compared_text: 比对件完整文本
        alignment: 预计算的段落对齐结果（可选）
        page_label: 页码标注
        base_confidence: 基础置信度

    Returns:
        DiffRecord 差异列表（已按页码和段落排序）
    """
    from .normalizer import split_paragraphs

    # 标准化
    orig_norm = normalize(original_text)
    comp_norm = normalize(compared_text)

    # 拆分段落
    orig_paras = split_paragraphs(orig_norm)
    comp_paras = split_paragraphs(comp_norm)

    # 段落对齐
    if alignment is None:
        from .aligner import align_paragraphs
        alignment = align_paragraphs(orig_paras, comp_paras)

    records = []

    # 逐段比对已对齐的段落对
    for pair in alignment.aligned:
        frags = _diff_text(pair.original_text, pair.compared_text)
        if not frags:
            continue  # 完全相同，不生成差异记录

        records.append(DiffRecord(
            id=str(uuid.uuid4()),
            page_label=page_label or f"原件段落{pair.original_index + 1} / 比对件段落{pair.compared_index + 1}",
            paragraph_index=pair.original_index,
            type='modified',
            original_text=pair.original_text,
            compared_text=pair.compared_text,
            confidence=base_confidence,
            fragments=frags,
            summary=_make_summary(frags),
        ))

    # 原件独有的段落 → "删除"
    for idx, text in alignment.deleted:
        records.append(DiffRecord(
            id=str(uuid.uuid4()),
            page_label=page_label or f"原件段落{idx + 1}",
            paragraph_index=idx,
            type='deleted',
            original_text=text,
            compared_text="（此条款在比对件中不存在）",
            confidence=base_confidence,
            summary="比对件中缺少此段落",
        ))

    # 比对件独有的段落 → "新增"
    for idx, text in alignment.added:
        records.append(DiffRecord(
            id=str(uuid.uuid4()),
            page_label=page_label or f"比对件段落{idx + 1}",
            paragraph_index=idx,
            type='added',
            original_text="（此条款在原件中不存在）",
            compared_text=text,
            confidence=base_confidence,
            summary="比对件中新增此段落",
        ))

    # 按类型排序: modified > deleted > added
    type_order = {'modified': 0, 'deleted': 1, 'added': 2}
    records.sort(key=lambda r: (type_order.get(r.type, 99), r.paragraph_index))

    logger.info(
        f"逐句比对完成: {len(records)} 条差异 "
        f"(修改{sum(1 for r in records if r.type == 'modified')}, "
        f"删除{sum(1 for r in records if r.type == 'deleted')}, "
        f"新增{sum(1 for r in records if r.type == 'added')})"
    )
    return records


def _cut_chinese(text: str) -> list[str]:
    """
    中文分词：优先使用 jieba，不可用时退化为字符级切分。

    对 SequenceMatcher 来说，字符级切分对中文已经足够好，
    因为 difflib 的算法会在字符序列中找到最佳匹配。
    """
    try:
        import jieba
        return list(jieba.cut(text))
    except ImportError:
        # 字符级切分作为回退（对中文比对效果依然可靠）
        return list(text)


def _diff_text(original: str, compared: str) -> List[DiffFragment]:
    """
    对一对已对齐段落做差异分析。

    使用 jieba/字符级分词 + SequenceMatcher，计算每个差异片段的
    字符级偏移量（original_start/end, compared_start/end），
    供前端 DiffItem 精确高亮使用。

    Args:
        original: 原件段落
        compared: 比对件段落

    Returns:
        DiffFragment 列表（空列表表示完全相同）
    """
    orig_tokens = _cut_chinese(original)
    comp_tokens = _cut_chinese(compared)

    # 构建 token → 原始文本字符偏移 映射
    orig_starts: list[int] = []
    pos = 0
    for t in orig_tokens:
        orig_starts.append(pos)
        pos += len(t)

    comp_starts: list[int] = []
    pos = 0
    for t in comp_tokens:
        comp_starts.append(pos)
        pos += len(t)

    sm = SequenceMatcher(None, orig_tokens, comp_tokens)
    fragments = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue

        # 计算字符偏移：将 token 索引映射回原始文本字符位置
        if i1 < i2:
            orig_start = orig_starts[i1]
            orig_end = orig_starts[i2 - 1] + len(orig_tokens[i2 - 1])
            orig_frag = original[orig_start:orig_end]
        else:
            # 纯插入，无原件文本
            orig_start = orig_starts[i1] if i1 < len(orig_starts) else len(original)
            orig_end = orig_start
            orig_frag = ""

        if j1 < j2:
            comp_start = comp_starts[j1]
            comp_end = comp_starts[j2 - 1] + len(comp_tokens[j2 - 1])
            comp_frag = compared[comp_start:comp_end]
        else:
            # 纯删除，无比对件文本
            comp_start = comp_starts[j1] if j1 < len(comp_starts) else len(compared)
            comp_end = comp_start
            comp_frag = ""

        fragments.append(DiffFragment(
            type=tag,        # 'replace' | 'delete' | 'insert'
            original=orig_frag,
            compared=comp_frag,
            original_start=orig_start,
            original_end=orig_end,
            compared_start=comp_start,
            compared_end=comp_end,
        ))

    return fragments


def _make_summary(fragments: List[DiffFragment]) -> str:
    """从差异片段生成人类可读的摘要。"""
    if not fragments:
        return "无差异"

    parts = []
    for f in fragments[:3]:  # 最多展示 3 个差异片段
        if f.type == 'replace':
            parts.append(f'"{f.original[:20]}" → "{f.compared[:20]}"')
        elif f.type == 'delete':
            parts.append(f'删除 "{f.original[:20]}"')
        elif f.type == 'insert':
            parts.append(f'新增 "{f.compared[:20]}"')

    if len(fragments) > 3:
        parts.append(f"... 等 {len(fragments)} 处差异")

    return '；'.join(parts)
