"""
段落智能对齐 — 找到原件 vs 比对件段落之间的最优对应关系。

策略:
    基于 SequenceMatcher.ratio() 的贪心匹配算法。
    相似度 ≥ 阈值 → 同一段落，否则标记为新增/删除。
"""

import logging
from difflib import SequenceMatcher
from typing import List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AlignedPair:
    """一对已对齐的段落。"""
    index: int                       # 对齐对序号
    original_text: str               # 原件段落文本
    compared_text: str               # 比对件段落文本
    similarity: float                # 相似度 (0-1)
    original_index: int              # 在原件中的段落索引
    compared_index: int              # 在比对件中的段落索引


@dataclass
class AlignmentResult:
    """段落对齐结果。"""
    aligned: List[AlignedPair] = field(default_factory=list)      # 已对齐的段落对
    deleted: List[Tuple[int, str]] = field(default_factory=list)  # 原件有、比对件无
    added: List[Tuple[int, str]] = field(default_factory=list)    # 比对件有、原件无
    similarity_threshold: float = 0.6


def align_paragraphs(
    original: List[str],
    compared: List[str],
    threshold: float = 0.6,
) -> AlignmentResult:
    """
    对两组文本段落列表进行智能对齐。

    Args:
        original: 原件段落列表
        compared: 比对件段落列表
        threshold: 相似度阈值，≥此值视为同一段落

    Returns:
        AlignmentResult 对齐结果
    """
    n, m = len(original), len(compared)
    result = AlignmentResult(similarity_threshold=threshold)

    if n == 0 and m == 0:
        return result
    if n == 0:
        for j, text in enumerate(compared):
            result.added.append((j, text))
        return result
    if m == 0:
        for i, text in enumerate(original):
            result.deleted.append((i, text))
        return result

    # Step 1: 构建 N×M 相似度矩阵
    pairs = []
    for i, orig_text in enumerate(original):
        for j, comp_text in enumerate(compared):
            sim = _text_similarity(orig_text, comp_text)
            if sim >= threshold:
                pairs.append((sim, i, j))

    # Step 2: 按相似度降序排列，贪心匹配
    pairs.sort(key=lambda x: x[0], reverse=True)

    matched_orig = set()
    matched_comp = set()

    for sim, i, j in pairs:
        if i not in matched_orig and j not in matched_comp:
            result.aligned.append(AlignedPair(
                index=len(result.aligned),
                original_text=original[i],
                compared_text=compared[j],
                similarity=sim,
                original_index=i,
                compared_index=j,
            ))
            matched_orig.add(i)
            matched_comp.add(j)

    # Step 3: 收集落单段落
    for i, text in enumerate(original):
        if i not in matched_orig:
            result.deleted.append((i, text))

    for j, text in enumerate(compared):
        if j not in matched_comp:
            result.added.append((j, text))

    logger.info(
        f"段落对齐完成: {len(result.aligned)} 对齐, "
        f"{len(result.deleted)} 删除, {len(result.added)} 新增"
    )
    return result


def _text_similarity(a: str, b: str) -> float:
    """
    计算两段文本的相似度。

    使用 SequenceMatcher 比较，对极短文本做惩罚。
    """
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    sm = SequenceMatcher(None, a, b)
    ratio = sm.ratio()

    # 短文本惩罚：文本越短，ratio 越不可靠
    min_len = min(len(a), len(b))
    if min_len < 10:
        ratio *= min_len / 10

    return ratio
