import type { DiffRecord, DiffSummary } from '../types/diff';

/**
 * 导出差异记录为 HTML 报告。
 * 使用 Electron 原生保存对话框。
 */
export async function exportToHTML(
  records: DiffRecord[],
  summary: DiffSummary | null,
): Promise<void> {
  const typeLabels: Record<string, string> = {
    modified: '修改',
    deleted: '删除',
    added: '新增',
  };

  const typeBadgeColors: Record<string, string> = {
    modified: '#f59e0b',
    deleted: '#ef4444',
    added: '#22c55e',
  };

  const rowsHTML = records.map(r => `
    <tr>
      <td><span class="badge" style="background:${typeBadgeColors[r.type]}">${typeLabels[r.type]}</span></td>
      <td>${r.pageLabel}</td>
      <td>${escapeHTML(r.originalText)}</td>
      <td>${escapeHTML(r.comparedText)}</td>
      <td>${(r.confidence * 100).toFixed(0)}%</td>
      <td>${escapeHTML(r.summary)}</td>
    </tr>
  `).join('');

  const html = `<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>合同比对报告</title>
  <style>
    body { font-family: -apple-system, system-ui, sans-serif; max-width: 1100px; margin: 0 auto; padding: 40px 20px; color: #1a1a1a; }
    h1 { text-align: center; font-size: 24px; margin-bottom: 8px; }
    .date { text-align: center; color: #888; margin-bottom: 24px; }
    .summary { display: flex; gap: 16px; justify-content: center; margin-bottom: 32px; }
    .summary-card { padding: 12px 24px; border-radius: 8px; text-align: center; background: #f5f5f5; }
    .summary-card .num { font-size: 28px; font-weight: 700; }
    .summary-card .label { font-size: 13px; color: #666; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 10px 12px; border: 1px solid #e0e0e0; text-align: left; font-size: 14px; }
    th { background: #f9fafb; font-weight: 600; }
    .badge { color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
    tr:nth-child(even) { background: #fafafa; }
  </style>
</head>
<body>
  <h1>📋 合同比对报告</h1>
  <p class="date">生成时间: ${new Date().toLocaleString('zh-CN')}</p>
  ${summary ? `
  <div class="summary">
    <div class="summary-card"><div class="num">${summary.total}</div><div class="label">总差异</div></div>
    <div class="summary-card"><div class="num">${summary.modified}</div><div class="label">修改</div></div>
    <div class="summary-card"><div class="num">${summary.deleted}</div><div class="label">删除</div></div>
    <div class="summary-card"><div class="num">${summary.added}</div><div class="label">新增</div></div>
  </div>` : ''}
  <table>
    <thead>
      <tr>
        <th>类型</th>
        <th>位置</th>
        <th>原件文本</th>
        <th>比对件文本</th>
        <th>置信度</th>
        <th>摘要</th>
      </tr>
    </thead>
    <tbody>
      ${rowsHTML}
    </tbody>
  </table>
</body>
</html>`;

  // 使用 Electron dialog 保存
  await saveFile('contract-diff-report.html', html);
}

/**
 * 导出差异记录为 CSV。
 */
export async function exportToCSV(records: DiffRecord[]): Promise<void> {
  const typeLabels: Record<string, string> = {
    modified: '修改',
    deleted: '删除',
    added: '新增',
  };

  const header = '类型,位置,原件文本,比对件文本,置信度,摘要\n';
  const rows = records.map(r => {
    const cells = [
      typeLabels[r.type],
      r.pageLabel,
      `"${r.originalText.replace(/"/g, '""')}"`,
      `"${r.comparedText.replace(/"/g, '""')}"`,
      `${(r.confidence * 100).toFixed(0)}%`,
      `"${r.summary.replace(/"/g, '""')}"`,
    ];
    return cells.join(',');
  }).join('\n');

  const bom = '﻿'; // BOM for Excel UTF-8 support
  await saveFile('contract-diff-records.csv', bom + header + rows);
}

// ── helpers ─────────────────────────────────────────────

function escapeHTML(text: string): string {
  const map: Record<string, string> = {
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#x27;',
  };
  return text.replace(/[&<>"']/g, c => map[c]);
}

async function saveFile(defaultName: string, content: string): Promise<void> {
  if (!window.electronAPI) {
    throw new Error('Electron API 不可用');
  }

  const savedPath = await window.electronAPI.saveFileDialog({
    defaultPath: defaultName,
    content,
  });

  if (savedPath === null) {
    // 用户取消了保存对话框
    return;
  }
}
