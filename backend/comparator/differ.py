"""
语义级比对引擎 — 对 OCR 行序不稳定性免疫。

核心思路：
    不依赖换行、标点做拆句（OCR 每次扫描结果不同），
    而用合同内容的自然结构标记（一、二、1、(一) 等）拆分语义单元，
    然后对语义单元做相似度比对。

策略自适应：
    - 双方含合同标记 → 合同结构拆分 + 单元比对
    - 有标记 vs 无标记 → 无标记侧全文本 + 有标记侧逐单元比对
    - 双方都无标记 → 降级为字符级全文比对
"""

import logging
import uuid
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import List
import re

from .normalizer import normalize

logger = logging.getLogger(__name__)


@dataclass
class DiffFragment:
    type: str                     # 'replace' | 'delete' | 'insert'
    original: str
    compared: str
    original_start: int = 0
    original_end: int = 0
    compared_start: int = 0
    compared_end: int = 0


@dataclass
class DiffRecord:
    id: str
    page_label: str
    paragraph_index: int
    type: str           # 'modified' | 'deleted' | 'added'
    original_text: str
    compared_text: str
    confidence: float
    fragments: List[DiffFragment] = field(default_factory=list)
    summary: str = ""
    page_index: int = -1              # 原件页码 (0-based), -1 表示不适用
    matched_page_index: int = -1      # 匹配到的比对件页码 (0-based), -1 表示不适用


# ── 可配置参数 ──────────────────────────────────────────

_HIGH_SIMILARITY = 0.995    # 去除格式后相似度 ≥ 此值视为内容一致(仅跳过完全相同的文本)
_FALLBACK_MERGE_GAP = 30    # 全文兜底比对时相邻差异合并的最大字符间隔

# ── 合同结构标记模式 ──────────────────────────────────────

_CONTRACT_MARKERS = re.compile(
    r'(?:^|\n)\s*('
    r'[一二三四五六七八九十]+\s*[\.\、，。．]|'          # 一、二、1. 2. (含ASCII句点)
    r'[（(][一二三四五六七八九十]+[)）]|'               # (一)(二)
    r'\d+\s*[\.\、，。．]|'                              # 1. 2. 3、
    r'\d+\s*[)）]|'                                      # 1) 2)
    r'[（(]\d+[)）]|'                                    # (1)(2)
    r'第[一二三四五六七八九十\d]+[条章节款项款目]|'         # 第一条、第二章
    r'[A-Z]\s*[\.\、]'                                   # A. B. (英文编号)
    r')'
)

# OCR 误识别修复：行首孤立标点
_OCR_BROKEN_MARKER = re.compile(r'(?:^|\n)\s*[、，、](?=\S)')

# 页码/噪声模式 — 匹配各种页码格式(行内任意位置)
_PAGE_NUMBER = re.compile(
    r'\s*(?:'
    r'第\s*\d+\s*页(\s*/\s*共\s*\d+\s*页)?|'         # 第X页/共N页
    r'[-\s]+\s*\d+\s*[-\s]+'                          # --- 5 ---
    r')[\s、。，]*',
)

# 水印/印章/扫描件常见噪声文字
_WATERMARK_NOISE = re.compile(
    r'[（(]?(?:机密文件|内部资料|扫描件|复印件|校验稿|草稿|初稿|终稿|定稿|存档|'
    r'仅供内部使用|不得外传|CONFIDENTIAL|INTERNAL|DRAFT|'
    r'合同专用章|财务专用章|公章|签字盖章页)[)）]?',
    re.IGNORECASE
)

# 标点/格式噪声字符（用于判断差异是否为实质性）
_SUBSTANTIVE_NOISE = re.compile(
    r'[\s、，。：；·．_,;:.\-·　\'\"\(\)（）\[\]【】〈〉《》！？…—　#\$%\^&\*\+=\|\\/`~@]+'
)


# ── 字符级差异分析（公共函数）─────────────────────────────


def _diff_text(original: str, compared: str) -> list:
    """
    两段文本的字符级差异分析。

    返回 DiffFragment 列表，包含精确的字符偏移量，
    前端可据此做逐字高亮。
    供 _unit_level_compare 和 line_matcher 共用。
    """
    sm = SequenceMatcher(None, original, compared)
    fragments = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue
        f_type = {'replace': 'replace', 'delete': 'delete', 'insert': 'insert'}[tag]
        fragments.append(DiffFragment(
            type=f_type,
            original=original[i1:i2] if tag in ('replace', 'delete') else '',
            compared=compared[j1:j2] if tag in ('replace', 'insert') else '',
            original_start=i1,
            original_end=i2,
            compared_start=j1,
            compared_end=j2,
        ))
    return fragments


def _has_substantive_diff(fragments: list) -> bool:
    """
    判断差异片段中是否包含实质性内容变更。

    去掉所有标点、空格、格式符号后，如果两边内容不同，
    说明是真实的内容变更（数字、文字等），而非纯格式噪声。

    示例：
        "1,000,000" vs "2,000,000" → 清洗后 "1000000" vs "2000000" → True
        "甲方：" vs "甲方:"           → 清洗后 "甲方" vs "甲方"     → False
    """
    for f in fragments:
        o_clean = _SUBSTANTIVE_NOISE.sub('', f.original)
        c_clean = _SUBSTANTIVE_NOISE.sub('', f.compared)
        if o_clean != c_clean:
            return True
    return False


def _make_summary(fragments: list) -> str:
    """
    从差异片段生成人类可读的摘要。
    """
    if not fragments:
        return "文本差异"
    parts = []
    for f in fragments[:3]:  # 最多取前3个片段的摘要
        if f.type == 'replace':
            o = f.original[:10].strip()
            c = f.compared[:10].strip()
            if o and c and o != c:
                parts.append(f"「{o}」→「{c}」")
            elif not o:
                parts.append(f"新增「{c}」")
            elif not c:
                parts.append(f"删除「{o}」")
        elif f.type == 'delete':
            parts.append(f"删除「{f.original[:15].strip()}」")
        elif f.type == 'insert':
            parts.append(f"新增「{f.compared[:15].strip()}」")
    result = '; '.join(parts)
    return result if result else "文本差异"


# ── 语义单元拆分 ──────────────────────────────────────────


def _split_contract(text: str) -> list[str]:
    """
    按段落拆分 — 空行分隔，一行一个语义单元。
    过滤：下划线占位符行、纯数字行。
    """
    paragraphs = re.split(r'\n\s*\n', text)
    units = []
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 纯下划线/空白占位符段落 → 跳过
        if re.match(r'^[_＿\s]+$', para):
            continue
        # 多行段落 → 拆为独立行
        if '\n' in para:
            for line in para.split('\n'):
                line = line.strip()
                if not line or re.match(r'^[_＿\s]+$', line) or re.match(r'^\d{1,3}$', line):
                    continue
                units.append(line)
        else:
            units.append(para)
    return units


def _split_generic(text: str) -> list[str]:
    """
    无合同标记时的通用拆分 — 按中文断句标点 + 自然段。
    """
    # 有双换行 → 先拆段落
    if '\n\n' in text:
        units = []
        for para in text.split('\n\n'):
            para = para.strip()
            if not para:
                continue
            # 段落内按句号拆
            sentences = re.split(r'(?<=[。！？])', para)
            units.extend(s.strip() for s in sentences if s.strip())
        return units

    # 纯单换行 → 去掉换行，按句号拆
    flat = text.replace('\n', '')
    if '。' in flat or '；' in flat:
        sentences = re.split(r'(?<=[。！？；])', flat)
        return [s.strip() for s in sentences if s.strip()]

    return [text]


# ── 语义单元级比对 ────────────────────────────────────────


def _unit_similarity(a: str, b: str) -> float:
    """两段文字的语义相似度。去掉编号前缀、空白、标点后比较。"""
def _strip_for_compare(s):
    # 去掉合同编号前缀（一、1、(一)等）
    s = _CONTRACT_MARKERS.sub('', s)
    # 去掉所有空白和标点
    s = re.sub(r'[\s、，。：；·．_,;:.\-·　]+', '', s)
    return s


def _unit_similarity(a: str, b: str) -> float:
    """两段文字的语义相似度。去掉编号前缀、空白、标点后比较。"""
    a_s = _strip_for_compare(a)
    b_s = _strip_for_compare(b)
    if not a_s and not b_s:
        return 1.0
    if not a_s or not b_s:
        return 0.0
    return SequenceMatcher(None, a_s, b_s).ratio()


def _unit_level_compare(
    o_units: list[str],
    c_units: list[str],
    page_label: str = "",
    base_confidence: float = 0.95,
) -> list:
    """
    语义单元级比对。

    对两组语义单元做 SequenceMatcher 对齐：
    - equal → 跳过
    - replace → 如果相似度 < 0.7 才标记为实质性差异
    - delete/insert → 标记为新增/删除
    """
    sm = SequenceMatcher(None, o_units, c_units)
    records = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            continue

        o_block = '\n'.join(o_units[i1:i2]).strip()
        c_block = '\n'.join(c_units[j1:j2]).strip()

        if not o_block and not c_block:
            continue

        if not o_block:
            records.append(DiffRecord(
                id=str(uuid.uuid4()),
                page_label=page_label or f"比对件新增",
                paragraph_index=i1,
                type='added',
                original_text='（原件中无此内容）',
                compared_text=c_block,
                confidence=base_confidence,
                summary=f"新增: {c_block[:50]}",
            ))
            continue

        if not c_block:
            records.append(DiffRecord(
                id=str(uuid.uuid4()),
                page_label=page_label or f"原件删除",
                paragraph_index=i1,
                type='deleted',
                original_text=o_block,
                compared_text='（比对件中无此内容）',
                confidence=base_confidence,
                summary=f"删除: {o_block[:50]}",
            ))
            continue

        # replace → 检查是否实质性差异
        # 去掉编号、标点后字符逐字完全一致 → 纯编号/格式变化, 跳过
        o_stripped = _strip_for_compare(o_block)
        c_stripped = _strip_for_compare(c_block)
        if o_stripped == c_stripped:
            continue

        stripped_sim = SequenceMatcher(None, o_stripped, c_stripped).ratio() if o_stripped and c_stripped else 0.0
        # 字符级差异分析：看看到底改了什么
        frags = _diff_text(o_block, c_block)

        # 去除格式后几乎一致 → 确认不是实质性内容变更再跳过
        if stripped_sim >= _HIGH_SIMILARITY:
            if not frags or not _has_substantive_diff(frags):
                continue

        if not frags:
            continue

        # 检查差异是否只是标点/空格/格式噪声
        if not _has_substantive_diff(frags):
            continue

        # 实质性修改
        raw_sim = SequenceMatcher(None, o_block, c_block).ratio()
        summary = _make_summary(frags)
        records.append(DiffRecord(
            id=str(uuid.uuid4()),
            page_label=page_label or f"条款变更",
            paragraph_index=i1,
            type='modified',
            original_text=o_block,
            compared_text=c_block,
            confidence=base_confidence * raw_sim,
            fragments=frags,
            summary=summary,
        ))

    return records


# ── 字符级全文比对（兜底）─────────────────────────────────


def _fulltext_fallback(
    orig: str, comp: str,
    page_label: str = "",
    base_confidence: float = 0.95,
) -> list:
    """无结构标记时的全文兜底比对。"""
    sm = SequenceMatcher(None, orig, comp)
    opcodes = list(sm.get_opcodes())

    merged = []
    buf = None
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == 'equal':
            if buf is not None and (i2 - i1) <= _FALLBACK_MERGE_GAP:
                buf['i2'] = i2
                buf['j2'] = j2
                continue
            else:
                if buf is not None:
                    merged.append(buf)
                    buf = None
                continue
        if buf is None:
            buf = {'tag': tag, 'i1': i1, 'i2': i2, 'j1': j1, 'j2': j2}
        else:
            buf['i2'] = i2
            buf['j2'] = j2
    if buf is not None:
        merged.append(buf)

    records = []
    for idx, m in enumerate(merged):
        o_block = orig[m['i1']:m['i2']].strip()
        c_block = comp[m['j1']:m['j2']].strip()
        if not o_block and not c_block:
            continue

        if not o_block:
            records.append(DiffRecord(
                id=str(uuid.uuid4()),
                page_label=page_label or f"差异{idx + 1}",
                paragraph_index=m['i1'],
                type='added',
                original_text='（原件中无此内容）',
                compared_text=c_block,
                confidence=base_confidence,
                summary=f"新增: {c_block[:50]}",
            ))
        elif not c_block:
            records.append(DiffRecord(
                id=str(uuid.uuid4()),
                page_label=page_label or f"差异{idx + 1}",
                paragraph_index=m['i1'],
                type='deleted',
                original_text=o_block,
                compared_text='（比对件中无此内容）',
                confidence=base_confidence,
                summary=f"删除: {o_block[:50]}",
            ))
        else:
            # 字符级差异分析
            frags = _diff_text(o_block, c_block)
            if not frags:
                continue
            # 过滤纯格式噪声
            if not _has_substantive_diff(frags):
                continue
            summary = _make_summary(frags)
            records.append(DiffRecord(
                id=str(uuid.uuid4()),
                page_label=page_label or f"差异{idx + 1}",
                paragraph_index=m['i1'],
                type='modified',
                original_text=o_block,
                compared_text=c_block,
                confidence=base_confidence,
                fragments=frags,
                summary=summary,
            ))
    return records


# ── 公开 API ──────────────────────────────────────────────


def compare(
    original_text: str,
    compared_text: str,
    page_label: str = "",
    base_confidence: float = 0.95,
) -> List[DiffRecord]:
    """
    自适应语义比对。

    Args:
        original_text: 原件文本
        compared_text: 比对件文本
        page_label: 页面标签
        base_confidence: 基础置信度

    Returns:
        DiffRecord 列表
    """
    if not original_text and not compared_text:
        return []

    orig = normalize(original_text)
    comp = normalize(compared_text)

    # 过滤页码/页眉/水印噪声
    orig = _PAGE_NUMBER.sub('', orig)
    comp = _PAGE_NUMBER.sub('', comp)
    orig = _WATERMARK_NOISE.sub('', orig)
    comp = _WATERMARK_NOISE.sub('', comp)
    orig = re.sub(r'\n{3,}', '\n\n', orig).strip()
    comp = re.sub(r'\n{3,}', '\n\n', comp).strip()

    # OCR 误识别修复：行首孤立标点 → 去除（OCR 丢失编号数字，残留 、 或 ，）
    orig = _OCR_BROKEN_MARKER.sub('\n', orig)
    comp = _OCR_BROKEN_MARKER.sub('\n', comp)

    # 检测是否有合同标记
    has_markers_o = bool(_CONTRACT_MARKERS.search(orig))
    has_markers_c = bool(_CONTRACT_MARKERS.search(comp))

    if has_markers_o and has_markers_c:
        # 双方都有合同标记 → 语义单元比对
        o_units = _split_contract(orig)
        c_units = _split_contract(comp)
        records = _unit_level_compare(
            o_units, c_units,
            page_label=page_label,
            base_confidence=base_confidence,
        )
    elif has_markers_o or has_markers_c:
        # 一方有标记 → 有标记侧拆单元，另一侧全文匹配
        if has_markers_o:
            o_units = _split_contract(orig)
            c_units = _split_generic(comp)
        else:
            o_units = _split_generic(orig)
            c_units = _split_contract(comp)
        records = _unit_level_compare(
            o_units, c_units,
            page_label=page_label,
            base_confidence=base_confidence,
        )
    else:
        # 双方都无标记 → 降级为全文比对
        flat_orig = orig.replace('\n', '')
        flat_comp = comp.replace('\n', '')
        records = _fulltext_fallback(
            flat_orig, flat_comp,
            page_label=page_label,
            base_confidence=base_confidence,
        )

    logger.info(
        f"比对完成: {len(records)} 条差异 "
        f"(修改{sum(1 for r in records if r.type == 'modified')}, "
        f"删除{sum(1 for r in records if r.type == 'deleted')}, "
        f"新增{sum(1 for r in records if r.type == 'added')})"
    )
    return records
