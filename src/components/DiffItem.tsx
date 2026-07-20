import type { DiffRecord } from '../types/diff';

interface Props {
  record: DiffRecord;
}

/** 差异卡片颜色映射 */
const TYPE_COLORS: Record<string, { bg: string; badge: string; label: string }> = {
  modified: { bg: '#fff8e1', badge: '#f59e0b', label: '修改' },
  deleted: { bg: '#ffeaea', badge: '#ef4444', label: '删除' },
  added: { bg: '#e8f5e9', badge: '#22c55e', label: '新增' },
};

/**
 * 单条差异卡片 — 展示原件 vs 比对件文本差异。
 */
export const DiffItem: React.FC<Props> = ({ record }) => {
  const colors = TYPE_COLORS[record.type] || TYPE_COLORS.modified;
  const isLowConfidence = record.confidence < 0.85;
  // 检查是否有低置信度片段
  const hasLowConfFrag = record.fragments.some(f => (f.ocrConfidence ?? 1) < 0.85);

  return (
    <div className={`diff-item ${isLowConfidence ? 'low-confidence' : ''}`} style={{ borderLeftColor: colors.badge }}>
      {/* 头部 */}
      <div className="diff-item-header">
        <span className="diff-badge" style={{ background: colors.badge }}>
          {colors.label}
        </span>
        <span className="diff-page-label">{record.pageLabel}</span>
        <span className={`diff-confidence ${isLowConfidence ? 'low' : ''}`}>
          {isLowConfidence ? '⚠️ ' : ''}
          OCR {(record.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {/* 内容 */}
      <div className="diff-item-body">
        {/* 原件 */}
        <div className="diff-text-block original-block">
          <span className="block-label">原件</span>
          <div className="block-content">
            {record.type === 'added' ? (
              <span className="text-absent">（此条款在原件中不存在）</span>
            ) : (
              <DiffText text={record.originalText} fragments={record.fragments} side="original" />
            )}
          </div>
        </div>

        {/* 比对件 */}
        <div className="diff-text-block compared-block">
          <span className="block-label">比对件</span>
          <div className="block-content">
            {record.type === 'deleted' ? (
              <span className="text-absent">（此条款在比对件中不存在）</span>
            ) : (
              <DiffText text={record.comparedText} fragments={record.fragments} side="compared" />
            )}
          </div>
        </div>
      </div>

      {/* 摘要 */}
      {record.summary && (
        <div className="diff-item-summary">
          📌 {record.summary}
        </div>
      )}
    </div>
  );
};

/**
 * 差异文本高亮渲染。
 * 使用后端提供的字符级偏移量 (originalStart/End, comparedStart/End)
 * 精确高亮差异位置，避免 indexOf 在重复文本上定位错误。
 */
const DiffText: React.FC<{
  text: string;
  fragments: DiffRecord['fragments'];
  side: 'original' | 'compared';
}> = ({ text, fragments, side }) => {
  if (!fragments || fragments.length === 0) {
    return <span>{text}</span>;
  }

  // 收集当前 side 的差异区间（从 fragment 的偏移量字段取）
  const sections: { start: number; end: number; type: string }[] = [];
  for (const f of fragments) {
    const start = side === 'original' ? f.originalStart : f.comparedStart;
    const end = side === 'original' ? f.originalEnd : f.comparedEnd;
    if (start < end) {
      sections.push({ start, end, type: f.type });
    }
  }

  if (sections.length === 0) return <span>{text}</span>;

  // 按位置排序
  sections.sort((a, b) => a.start - b.start);

  // 合并重叠/相邻区间
  const merged: typeof sections = [];
  for (const s of sections) {
    if (merged.length === 0 || s.start >= merged[merged.length - 1].end) {
      merged.push(s);
    } else {
      merged[merged.length - 1].end = Math.max(merged[merged.length - 1].end, s.end);
    }
  }

  // 构建高亮片段
  const parts: React.ReactNode[] = [];
  let pos = 0;

  for (let i = 0; i < merged.length; i++) {
    const s = merged[i];

    // 差异前的相同文本
    if (s.start > pos) {
      parts.push(<span key={`eq-${i}`}>{text.slice(pos, s.start)}</span>);
    }

    // 差异文本 — 原件侧标红（删除/替换），比对件侧标绿（插入/替换）
    const className =
      side === 'original'
        ? s.type === 'delete' || s.type === 'replace' ? 'text-deleted' : ''
        : s.type === 'insert' || s.type === 'replace' ? 'text-inserted' : '';

    parts.push(
      <span key={`diff-${i}`} className={className || undefined}>
        {text.slice(s.start, s.end)}
      </span>
    );

    pos = s.end;
  }

  // 尾部相同文本
  if (pos < text.length) {
    parts.push(<span key="eq-trail">{text.slice(pos)}</span>);
  }

  return <>{parts}</>;
};
