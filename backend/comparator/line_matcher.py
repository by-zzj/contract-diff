"""
行级滑动窗口匹配 — OCR vs Word 行级贪心对齐。

核心场景：OCR 输出无段落边界（单 \n 行），Word 文本有自然段落（\n\n），
段落对齐完全失败。行级匹配在字符行粒度上做对齐，配合滑动窗口防止
重复表头/页脚误匹配。

算法：
1. 双方文本按 \n 拆分为行
2. 对 OCR 第 i 行，在 Word 行 [j-w, j+w] 窗口内找最佳匹配
   （j = i * (word_lines / ocr_lines)，线性投影）
3. SequenceMatcher.ratio() > 0.75 → 对齐对
4. 对齐对相似度 < 0.95 → 字符级差异
5. 未匹配 OCR 行 → deleted；未匹配 Word 行 → added
"""

import logging
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class LineMatchResult:
    """行级对齐结果。"""
    aligned: list = field(default_factory=list)   # [(ocr_idx, word_idx, similarity)]
    ocr_deleted: list = field(default_factory=list)  # [(ocr_idx, text)]
    word_added: list = field(default_factory=list)   # [(word_idx, text)]


def line_level_align(
    ocr_lines: List[str],
    word_lines: List[str],
    threshold: float = 0.75,
    window: int = 5,
) -> LineMatchResult:
    """
    OCR 行列表 vs Word 行列表的滑动窗口贪心匹配。

    Args:
        ocr_lines: OCR 输出的行（\n 分割）
        word_lines: Word 文本的行（\n 分割，\n\n 段落已展开）
        threshold: 相似度阈值，>= 此值视为匹配
        window: 搜索窗口半径（默认 5）

    Returns:
        LineMatchResult 对齐结果
    """
    n_ocr = len(ocr_lines)
    n_word = len(word_lines)

    result = LineMatchResult()

    if n_ocr == 0 and n_word == 0:
        return result
    if n_ocr == 0:
        for j, text in enumerate(word_lines):
            if text.strip('_ \t\r　·'):
                result.word_added.append((j, text))
        return result
    if n_word == 0:
        for i, text in enumerate(ocr_lines):
            if text.strip('_ \t\r　·'):
                result.ocr_deleted.append((i, text))
        return result

    # 构建相似度矩阵（仅窗口内）
    used_word = set()
    pairs = []
    for i, o_line in enumerate(ocr_lines):
        projected_j = int(i * n_word / n_ocr)
        j_start = max(0, projected_j - window)
        j_end = min(n_word, projected_j + window + 1)
        for j in range(j_start, j_end):
            if j in used_word:
                continue
            w_line = word_lines[j]
            sim = _line_similarity(o_line, w_line)
            if sim >= threshold:
                pairs.append((sim, i, j))

    # 贪心匹配
    pairs.sort(key=lambda x: x[0], reverse=True)
    matched_ocr = set()
    for sim, i, j in pairs:
        if i not in matched_ocr and j not in used_word:
            result.aligned.append((i, j, sim))
            matched_ocr.add(i)
            used_word.add(j)

    # 未匹配 OCR 行 → deleted
    for i, text in enumerate(ocr_lines):
        if i not in matched_ocr and text.strip('_ \t\r　·'):
            result.ocr_deleted.append((i, text))

    # 未匹配 Word 行 → added
    for j, text in enumerate(word_lines):
        if j not in used_word and text.strip('_ \t\r　·'):
            result.word_added.append((j, text))

    logger.info(
        f"行级对齐: {len(result.aligned)} 对齐, "
        f"{len(result.ocr_deleted)} 删除, {len(result.word_added)} 新增"
    )
    return result


def line_level_compare(
    ocr_text: str,
    word_text: str,
    page_label: str = "",
    base_confidence: float = 0.95,
    threshold: float = 0.75,
    window: int = 5,
) -> list:
    """
    OCR vs Word 行级比对入口。

    Args:
        ocr_text: OCR 识别文本（\n 分隔行）
        word_text: Word 提取文本（\n\n 段落）
        page_label: 页面标签
        base_confidence: 基础置信度
        threshold: 行相似度阈值
        window: 滑动窗口半径

    Returns:
        DiffRecord 列表
    """
    from .differ import _diff_text, _make_summary, DiffRecord

    # Step 1: 拆分并统一粒度
    ocr_lines_raw = [l.strip() for l in ocr_text.split('\n') if l.strip('_ \t\r　·')]
    word_lines_raw = []
    for para in word_text.split('\n\n'):
        for line in para.split('\n'):
            stripped = line.strip()
            if stripped:
                word_lines_raw.append(stripped)

    # OCR 短行合并：将 < 15 字符的相邻行合并到合理长度
    ocr_lines = _merge_short_lines(ocr_lines_raw, min_len=15)

    # Word 长行拆分：将 > 40 字符的行按句子拆分
    word_lines = []
    for line in word_lines_raw:
        if len(line) > 40:
            # 在中文标点处拆分
            parts = _split_long_line(line, max_len=40)
            word_lines.extend(parts)
        else:
            word_lines.append(line)

    # Step 2: 行级对齐
    alignment = line_level_align(
        ocr_lines, word_lines, threshold=threshold, window=window
    )

    records = []

    # Step 3a: 已对齐行 → 差异分析
    for o_idx, w_idx, sim in alignment.aligned:
        o_line = ocr_lines[o_idx]
        w_line = word_lines[w_idx]
        if sim >= 0.95:
            continue  # 几乎一致，跳过
        frags = _diff_text(o_line, w_line)
        if not frags:
            continue
        # 跳过纯单字符差异（OCR 噪声）
        if len(frags) == 1 and frags[0].type == 'replace':
            if len(frags[0].original) <= 1 and len(frags[0].compared) <= 1:
                continue
        records.append(DiffRecord(
            id=str(uuid.uuid4()),
            page_label=page_label or f"原件第{o_idx + 1}行 -> 比对件第{w_idx + 1}行",
            paragraph_index=o_idx,
            type='modified',
            original_text=o_line,
            compared_text=w_line,
            confidence=base_confidence * sim,
            fragments=frags,
            summary=_make_summary(frags),
        ))

    # Step 3b: OCR 独有行 → deleted
    for o_idx, text in alignment.ocr_deleted:
        records.append(DiffRecord(
            id=str(uuid.uuid4()),
            page_label=page_label or f"原件第{o_idx + 1}行",
            paragraph_index=o_idx,
            type='deleted',
            original_text=text,
            compared_text='（此内容在比对件中不存在）',
            confidence=base_confidence,
            fragments=[],
            summary=f"删除: {text[:40]}",
        ))

    # Step 3c: Word 独有行 → added
    for w_idx, text in alignment.word_added:
        records.append(DiffRecord(
            id=str(uuid.uuid4()),
            page_label=page_label or f"比对件新增",
            paragraph_index=w_idx,
            type='added',
            original_text='（此内容在原件中不存在）',
            compared_text=text,
            confidence=base_confidence,
            fragments=[],
            summary=f"新增: {text[:40]}",
        ))

    logger.info(
        f"行级比对完成: {len(records)} 条差异 "
        f"(修改{sum(1 for r in records if r.type == 'modified')}, "
        f"删除{sum(1 for r in records if r.type == 'deleted')}, "
        f"新增{sum(1 for r in records if r.type == 'added')})"
    )
    return records


def _line_similarity(a: str, b: str) -> float:
    """计算两行文本的相似度。"""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    a_clean = a.strip('_ \t\r　·')
    b_clean = b.strip('_ \t\r　·')
    if not a_clean or not b_clean:
        return 0.0

    # 基础比率
    ratio = SequenceMatcher(None, a_clean, b_clean).ratio()

    # 对于短行，用 Jaccard 字符集重叠做补偿
    min_len = min(len(a_clean), len(b_clean))
    if min_len < 15:
        set_a = set(a_clean)
        set_b = set(b_clean)
        if set_a and set_b:
            jaccard = len(set_a & set_b) / len(set_a | set_b)
            ratio = max(ratio, jaccard * 0.6)

    return ratio


def _merge_short_lines(lines: list, min_len: int = 15) -> list:
    """合并相邻的短行，直到达到 min_len 或遇到长行。"""
    result = []
    buf = []
    for line in lines:
        buf.append(line)
        combined_len = sum(len(l) for l in buf)
        if combined_len >= min_len:
            result.append(' '.join(buf))
            buf = []
    if buf:
        result.append(' '.join(buf))
    return result


def _split_long_line(line: str, max_len: int = 40) -> list:
    """在中文标点处拆分过长行。"""
    import re
    if len(line) <= max_len:
        return [line]
    parts = re.split(r'(?<=[。，；：、,!?])', line)
    result = []
    buf = []
    for p in parts:
        buf.append(p)
        if sum(len(b) for b in buf) >= max_len:
            result.append(''.join(buf))
            buf = []
    if buf:
        result.append(''.join(buf))
    return result if result else [line]
