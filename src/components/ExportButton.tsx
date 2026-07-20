import { useState } from 'react';
import type { DiffRecord, DiffSummary } from '../types/diff';
import { exportToHTML, exportToCSV } from '../utils/export';
import { logger } from '../utils/logger';

interface Props {
  records: DiffRecord[];
  summary: DiffSummary | null;
}

/**
 * 导出按钮组件 — 支持 HTML 报告和 CSV 导出。
 */
export const ExportButton: React.FC<Props> = ({ records, summary }) => {
  const [exporting, setExporting] = useState(false);

  const handleExportHTML = async () => {
    setExporting(true);
    try {
      await exportToHTML(records, summary);
    } catch (err: any) {
      logger.error('HTML export failed', err);
    } finally {
      setExporting(false);
    }
  };

  const handleExportCSV = async () => {
    setExporting(true);
    try {
      await exportToCSV(records);
    } catch (err: any) {
      logger.error('CSV export failed', err);
    } finally {
      setExporting(false);
    }
  };

  if (records.length === 0) return null;

  return (
    <div className="export-buttons">
      <button
        className="btn-export html-export"
        onClick={handleExportHTML}
        disabled={exporting}
      >
        📄 导出 HTML 报告
      </button>
      <button
        className="btn-export csv-export"
        onClick={handleExportCSV}
        disabled={exporting}
      >
        📊 导出 CSV
      </button>
    </div>
  );
};
