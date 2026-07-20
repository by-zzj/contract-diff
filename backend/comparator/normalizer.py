"""
文本标准化 — 消除格式差异对文本比对的干扰。

处理:
    - 全角字符 → 半角（数字、字母、符号）
    - 换行符统一
    - 空格规范化
    - 标点符号统一
    - 不可见字符过滤
"""

import re
from typing import List


def normalize(text: str) -> str:
    """
    标准化 OCR 输出的原始文本。

    Args:
        text: 原始 OCR 文本

    Returns:
        标准化后的文本
    """
    if not text:
        return ""

    # 1. 统一换行符
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # 2. 全角转半角
    text = _full_to_half(text)

    # 3. 合并连续空行（≥3 个空行 → 2 个空行，作为段落分隔）
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 4. 移除中文之间的空格（中文内部不应有空格）
    text = re.sub(r'(?<=[一-鿿])\s+(?=[一-鿿])', '', text)

    # 5. 中文字符与数字/字母之间的空格标准化（保留一个半角空格）
    text = re.sub(
        r'(?<=[一-鿿])\s+(?=[a-zA-Z0-9])',
        ' ', text,
    )
    text = re.sub(
        r'(?<=[a-zA-Z0-9])\s+(?=[一-鿿])',
        ' ', text,
    )

    # 6. 统一中文标点符号
    text = _normalize_punctuation(text)

    # 7. 移除控制字符（保留换行符和制表符）
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

    # 8. 清理首尾空白
    text = text.strip()

    return text


def split_paragraphs(text: str) -> List[str]:
    """
    将标准化后的文本拆分为段落列表。

    Args:
        text: 标准化后的文本

    Returns:
        段落列表（已去空段落）
    """
    paragraphs = re.split(r'\n\s*\n', text)
    return [p.strip() for p in paragraphs if p.strip()]


def split_sentences(paragraph: str) -> List[str]:
    """
    将段落拆分为句子。

    中文断句依据: 。！？；\n

    Args:
        paragraph: 段落文本

    Returns:
        句子列表
    """
    # 按中文标点断句
    sentences = re.split(r'(?<=[。！？；])\s*', paragraph)
    return [s.strip() for s in sentences if s.strip()]


# ── 内部辅助 ──────────────────────────────────────────────

def _full_to_half(text: str) -> str:
    """全角字符转半角。"""
    result = []
    for ch in text:
        code = ord(ch)
        # 全角数字 ０-９ → 0-9
        if 0xFF10 <= code <= 0xFF19:
            result.append(chr(code - 0xFEE0))
        # 全角大写字母 Ａ-Ｚ → A-Z
        elif 0xFF21 <= code <= 0xFF3A:
            result.append(chr(code - 0xFEE0))
        # 全角小写字母 ａ-ｚ → a-z
        elif 0xFF41 <= code <= 0xFF5A:
            result.append(chr(code - 0xFEE0))
        # 全角常见符号
        elif code == 0xFF08:   # （ → (
            result.append('(')
        elif code == 0xFF09:   # ） → )
            result.append(')')
        elif code == 0xFF0C:   # ， → ,
            result.append(',')
        elif code == 0x3001:   # 、保持
            result.append(ch)
        elif code == 0x3002:   # 。保持
            result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)


def _normalize_punctuation(text: str) -> str:
    """统一中文标点符号。"""
    replacements = {
        '﹐': '，',
        '﹔': '；',
        '﹕': '：',
        '﹖': '？',
        '﹗': '！',
        '｀': '·',
        # OCR 常见混淆
        '巳': '已',     # 已
        '曰': '日',     # 日
        '末': '未',     # 未
        '士': '土',     # 土
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text
