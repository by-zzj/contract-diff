"""
文本标准化 — 消除 OCR 噪音和格式差异，为比对做准备。

设计原则：
    - 一次清洗：所有文本在此统一标准化，不需反复清洗
    - 对标点宽容：OCR 同一字符每次可能识别为不同标点，统一规整
    - 保留语义：清洗操作不可改变文本含义
"""

import re
from typing import List


def normalize(text: str) -> str:
    """主标准化入口 — 所有比对文本必经此函数。"""
    if not text:
        return ""

    # 0. OCR 空格归一化：数字与相邻中文之间的多余空格
    #    "2026 年 7 月 15 日" → "2026年7月15日"
    #    "168 号" → "168号"、 "第 3 条" → "第3条"
    #    数字间空格保留（"1001 2345" 可能是两个独立编号）
    text = re.sub(r'(?<=\d)\s+(?=[一-鿿])', '', text)  # 数字后+汉字前
    text = re.sub(r'(?<=[一-鿿])\s+(?=\d)', '', text)  # 汉字后+数字前

    # 1. 统一换行符
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # 2. 全角→半角（数字、字母、常见符号）
    text = _full_to_half(text)

    # 3. OCR 不稳定标点 → 统一归一化
    #    同一字符可能被 OCR 识别为: 、 ' ， ' ' · 等
    text = _normalize_punctuation(text)

    # 4. 下划线/全角空格/点 → 普通空格
    text = re.sub(r'[_　·]+', ' ', text)
    # 连续空格 → 单空格
    text = re.sub(r' +', ' ', text)

    # 5. 中文之间去除空格
    text = re.sub(r'(?<=[一-鿿])\s+(?=[一-鿿])', '', text)

    # 6. 中文字与数字/字母间保留一个半角空格
    text = re.sub(r'(?<=[一-鿿])\s+(?=[a-zA-Z0-9])', ' ', text)
    text = re.sub(r'(?<=[a-zA-Z0-9])\s+(?=[一-鿿])', ' ', text)

    # 7. 合并连续空行（3+ → 2）
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 8. 去除控制字符（保留换行和制表符）
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

    # 9. 零宽字符、BOM
    text = text.replace('​', '').replace('‌', '').replace('‍', '')
    text = text.replace('﻿', '')

    # 10. 清理首尾
    text = text.strip()

    return text


def split_paragraphs(text: str) -> List[str]:
    """按双换行拆分段落。"""
    paragraphs = re.split(r'\n\s*\n', text)
    return [p.strip() for p in paragraphs if p.strip()]


def split_sentences(text: str) -> List[str]:
    """按中文标点拆分为句子，保留分隔符。"""
    sentences = re.split(r'(?<=[。！？；])\s*', text)
    return [s.strip() for s in sentences if s.strip()]


def to_comparable(text: str) -> str:
    """
    将文本转为"可比对形式"：去空格、去换行、归一化标点。
    比较两段文本是否"语义相同"时用此函数。
    """
    # 去除所有空白
    t = re.sub(r'\s+', '', text)
    # 统一括号
    t = t.replace('(', '（').replace(')', '）')
    return t


# ── 内部辅助 ──────────────────────────────────────────────

def _full_to_half(text: str) -> str:
    """全角字符转半角。"""
    result = []
    for ch in text:
        code = ord(ch)
        if 0xFF10 <= code <= 0xFF19:     # 数字
            result.append(chr(code - 0xFEE0))
        elif 0xFF21 <= code <= 0xFF3A:   # 大写字母
            result.append(chr(code - 0xFEE0))
        elif 0xFF41 <= code <= 0xFF5A:   # 小写字母
            result.append(chr(code - 0xFEE0))
        elif code == 0xFF08:              # （
            result.append('(')
        elif code == 0xFF09:              # ）
            result.append(')')
        elif code == 0xFF0C:              # ，
            result.append(',')
        else:
            result.append(ch)
    return ''.join(result)


def _normalize_punctuation(text: str) -> str:
    """统一 OCR 不稳定的标点符号。"""
    # 中文标点变体统一
    replacements = {
        '﹐': '，', '﹔': '；', '﹕': '：', '﹖': '？', '﹗': '！',
        '｀': '·',
        # OCR 常见混淆标点（这些字符在 OCR 输出中不稳定）
        '‘': '、', '\'': '、', '"': '"', '"': '"',
        '˙': '。',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    # 连续标点去重（OCR 可能输出 。。。。 或 ······ 等）
    text = re.sub(r'[。．。]{2,}', '。', text)
    text = re.sub(r'[、]{2,}', '、', text)
    text = re.sub(r'[·]{3,}', '。', text)

    return text
