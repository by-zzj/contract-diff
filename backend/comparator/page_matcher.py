"""
页面级匹配引擎 — 多页合同的逐页对齐比对.

核心思路:
    多页合同的比对不能简单将所有页面文本拼接后全文比对。
    应该先做页面级对齐(找到原件第i页对应比对件第j页),
    再对每对已对齐的页面做逐页差异分析。

    复用现有的 aligner.align_paragraphs() — 每个页面作为一个"段落",
    利用其 N×M 相似度矩阵 + 贪心匹配机制。

特性:
    - 页序不一致 → 相似度矩阵找到最佳匹配, 不依赖页码顺序
    - 页数不等 → 未匹配页标记为 deleted 或 added
    - 重复页面 → 贪心匹配避免重复, 相似度最高的先配
    - 页码信息 → 结果中包含原件和比对件的页码
"""
import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

from .aligner import align_paragraphs, AlignmentResult

logger = logging.getLogger(__name__)


@dataclass
class PageMatchResult:
    """页面级对齐 + 差异比对结果."""
    matched_pairs: list = field(default_factory=list)
    # [(orig_page_idx, comp_page_idx, similarity, diff_records)]

    unmatched_original: list = field(default_factory=list)
    # [(orig_page_idx, text)] — 原件有但比对件无的页面

    unmatched_compared: list = field(default_factory=list)
    # [(comp_page_idx, text)] — 比对件有但原件无的页面

    all_records: list = field(default_factory=list)
    # 所有 DiffRecord 的汇总列表

    summary: dict = field(default_factory=lambda: {
        "total": 0, "modified": 0, "deleted": 0, "added": 0,
    })

    page_alignment: list = field(default_factory=list)
    # 对齐关系详情 [{orig_page, comp_page, similarity}]


def match_and_compare_pages(
    original_pages: list[dict],
    compared_pages: list[dict],
    page_threshold: float = 0.5,
    strategy: str = "auto",
) -> PageMatchResult:
    """
    多页合同的逐页对齐比对。

    Args:
        original_pages: 原件页面列表
            [{text, page_index, confidence, source_file, is_ocr}]
        compared_pages: 比对件页面列表 (同上格式)
        page_threshold: 页面级对齐相似度阈值(0-1), 默认 0.5
        strategy: 策略提示("ocr"/"word"/"auto"), 用于日志

    Returns:
        PageMatchResult 包含对齐关系 + 所有差异记录
    """
    n_orig = len(original_pages)
    n_comp = len(compared_pages)

    logger.info(
        f"逐页对齐: 原件{n_orig}页 vs 比对件{n_comp}页, "
        f"页面阈值={page_threshold}, 策略={strategy}"
    )

    result = PageMatchResult()

    if n_orig == 0 and n_comp == 0:
        return result

    if n_orig == 0:
        for j, page in enumerate(compared_pages):
            text = page.get("text", "")
            if text.strip():
                result.unmatched_compared.append((j, text))
        _add_unmatched_records(result, original_pages, compared_pages)
        return result

    if n_comp == 0:
        for i, page in enumerate(original_pages):
            text = page.get("text", "")
            if text.strip():
                result.unmatched_original.append((i, text))
        _add_unmatched_records(result, original_pages, compared_pages)
        return result

    # Step 1: 提取每页的纯文本
    orig_texts = [p.get("text", "") for p in original_pages]
    comp_texts = [p.get("text", "") for p in compared_pages]

    # 过滤空文本页
    valid_orig = [(i, t) for i, t in enumerate(orig_texts) if t.strip()]
    valid_comp = [(j, t) for j, t in enumerate(comp_texts) if t.strip()]

    if not valid_orig and not valid_comp:
        return result

    # Step 2: 复用 align_paragraphs() 做页面级对齐
    # 每个页面的文本作为一个"段落"
    alignment: AlignmentResult = align_paragraphs(
        original=[t for _, t in valid_orig],
        compared=[t for _, t in valid_comp],
        threshold=page_threshold,
    )

    logger.info(
        f"页面匹配: {len(alignment.aligned)} 对齐, "
        f"{len(alignment.deleted)} 原件独有, "
        f"{len(alignment.added)} 比对件独有"
    )

    # Step 3: 记录对齐关系
    for ap in alignment.aligned:
        orig_idx = valid_orig[ap.original_index][0]
        comp_idx = valid_comp[ap.compared_index][0]
        result.page_alignment.append({
            "orig_page": orig_idx,
            "comp_page": comp_idx,
            "similarity": ap.similarity,
        })

    # Step 4: 已对齐页面 → 逐页比对
    from .differ import compare as page_compare
    from .normalizer import normalize

    base_conf = min(
        (p.get("confidence", 0.95) for p in original_pages),
        default=0.95
    )
    base_conf = min(base_conf, min(
        (p.get("confidence", 0.95) for p in compared_pages),
        default=0.95
    ))

    for ap in alignment.aligned:
        orig_idx = valid_orig[ap.original_index][0]
        comp_idx = valid_comp[ap.compared_index][0]
        o_text = orig_texts[orig_idx]
        c_text = comp_texts[comp_idx]

        # 检查内容是否实质相同
        n_o = normalize(o_text)
        n_c = normalize(c_text)
        from difflib import SequenceMatcher
        raw_sim = SequenceMatcher(None, n_o, n_c).ratio()

        # 高相似度 (>0.98) 且 normalize 后一致 → 跳过逐字比对
        if raw_sim >= 0.98 and n_o == n_c:
            result.matched_pairs.append((orig_idx, comp_idx, ap.similarity, []))
            continue

        # 逐页差异分析
        page_records = page_compare(
            original_text=o_text,
            compared_text=c_text,
            page_label=f"原件第{orig_idx + 1}页 vs 比对件第{comp_idx + 1}页",
            base_confidence=base_conf * ap.similarity,
        )

        # 在每条差异记录中附加页码信息
        for r in page_records:
            r.page_index = orig_idx
            r.matched_page_index = comp_idx

        result.matched_pairs.append((orig_idx, comp_idx, ap.similarity, page_records))
        result.all_records.extend(page_records)

    # Step 5: 未匹配页面
    for idx_in_aligned, text in alignment.deleted:
        orig_idx = valid_orig[idx_in_aligned][0]
        result.unmatched_original.append((orig_idx, text))

    for idx_in_aligned, text in alignment.added:
        comp_idx = valid_comp[idx_in_aligned][0]
        result.unmatched_compared.append((comp_idx, text))

    # Step 6: 生成删除/新增记录
    _add_unmatched_records(result, original_pages, compared_pages)

    # Step 7: 计算汇总
    result.summary = {
        "total": len(result.all_records),
        "modified": sum(1 for r in result.all_records if r.type == "modified"),
        "deleted": sum(1 for r in result.all_records if r.type == "deleted"),
        "added": sum(1 for r in result.all_records if r.type == "added"),
    }

    logger.info(
        f"逐页比对完成: {result.summary['total']} 条差异 "
        f"(修改{result.summary['modified']}, "
        f"删除{result.summary['deleted']}, "
        f"新增{result.summary['added']})"
    )

    return result


def _add_unmatched_records(result, orig_pages, comp_pages):
    """为未匹配页面生成 DiffRecord."""
    from .differ import DiffRecord

    base_conf = 0.95
    if orig_pages:
        base_conf = min(p.get("confidence", 0.95) for p in orig_pages)
    if comp_pages:
        base_conf = min(base_conf, min(p.get("confidence", 0.95) for p in comp_pages))

    for orig_idx, text in result.unmatched_original:
        record = DiffRecord(
            id=str(uuid.uuid4()),
            page_label=f"原件第{orig_idx + 1}页（对比件中无对应页）",
            paragraph_index=-1,
            type="deleted",
            original_text=text,
            compared_text="（比对件中无对应页面）",
            confidence=base_conf,
            summary=f"整页缺失: 原件第{orig_idx + 1}页",
        )
        record.page_index = orig_idx
        record.matched_page_index = -1
        result.all_records.append(record)

    for comp_idx, text in result.unmatched_compared:
        record = DiffRecord(
            id=str(uuid.uuid4()),
            page_label=f"比对件第{comp_idx + 1}页（原件中无对应页）",
            paragraph_index=-1,
            type="added",
            original_text="（原件中无对应页面）",
            compared_text=text,
            confidence=base_conf,
            summary=f"整页新增: 比对件第{comp_idx + 1}页",
        )
        record.page_index = -1
        record.matched_page_index = comp_idx
        result.all_records.append(record)
