"""文本比对模块。"""
from .normalizer import normalize, split_paragraphs, split_sentences
from .aligner import align_paragraphs, AlignedPair, AlignmentResult
from .differ import compare, DiffFragment, DiffRecord
