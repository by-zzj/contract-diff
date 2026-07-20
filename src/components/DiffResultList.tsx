import type { DiffRecord, DiffSummary } from '../types/diff';
import { DiffItem } from './DiffItem';

interface Props {
  records: DiffRecord[];
  summary: DiffSummary | null;
  activeFilter: string;
  onFilterChange: (filter: string) => void;
  onBack: () => void;
}

/**
 * 差异结果列表 — 汇总差异数量 + 逐条展示 + 筛选 + 导出入口。
 */
export const DiffResultList: React.FC<Props> = ({
  records,
  summary,
  activeFilter,
  onFilterChange,
  onBack,
}) => {
  const filters = [
    { key: 'all', label: '全部' },
    { key: 'modified', label: '修改' },
    { key: 'deleted', label: '删除' },
    { key: 'added', label: '新增' },
  ];

  return (
    <div className="diff-result-list">
      {/* 顶部栏 */}
      <div className="result-header">
        <button className="btn-back" onClick={onBack}>
          ← 返回
        </button>
        <h2 className="result-title">
          比对结果
          {summary && (
            <span className="result-count">共 {summary.total} 处差异</span>
          )}
        </h2>
      </div>

      {/* 统计卡片 */}
      {summary && (
        <div className="summary-cards">
          <div className="summary-card total">
            <span className="summary-num">{summary.total}</span>
            <span className="summary-label">总差异</span>
          </div>
          <div className="summary-card modified">
            <span className="summary-num">{summary.modified}</span>
            <span className="summary-label">修改</span>
          </div>
          <div className="summary-card deleted">
            <span className="summary-num">{summary.deleted}</span>
            <span className="summary-label">删除</span>
          </div>
          <div className="summary-card added">
            <span className="summary-num">{summary.added}</span>
            <span className="summary-label">新增</span>
          </div>
        </div>
      )}

      {/* 筛选栏 */}
      <div className="filter-bar">
        {filters.map(f => (
          <button
            key={f.key}
            className={`filter-btn ${activeFilter === f.key ? 'active' : ''}`}
            onClick={() => onFilterChange(f.key)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* 差异列表 */}
      <div className="diff-items">
        {records.length === 0 ? (
          <div className="empty-result">
            <span className="empty-icon">✅</span>
            <p>未发现差异，两份合同内容一致。</p>
          </div>
        ) : (
          records.map(r => <DiffItem key={r.id} record={r} />)
        )}
      </div>
    </div>
  );
};
