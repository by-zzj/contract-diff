import { useCallback, useState } from 'react';
import { usePythonBridge } from './hooks/usePythonBridge';
import { useDiffState } from './hooks/useDiffState';
import { logger } from './utils/logger';
import { FileImporter } from './components/FileImporter';
import { FileGroupList } from './components/FileGroupList';
import { ProcessingStatus } from './components/ProcessingStatus';
import { DiffResultList } from './components/DiffResultList';
import { ExportButton } from './components/ExportButton';
import { OcrPreviewPanel } from './components/OcrPreviewPanel';

/**
 * 应用主组件。
 *
 * 状态流转:
 *   import → processing → result
 */
const App: React.FC = () => {
  const bridge = usePythonBridge();
  const diff = useDiffState();
  const [operationError, setOperationError] = useState<string | null>(null);
  // OCR 预览文本
  const [ocrPreview, setOcrPreview] = useState<{
    original: { fileName: string; text: string; confidence: number }[];
    compared: { fileName: string; text: string; confidence: number }[];
  } | null>(null);

  // ── 开始比对 ──────────────────────────────────────────

  const handleStartCompare = useCallback(async () => {
    const originalPaths = diff.files
      .filter(f => f.group === 'original')
      .map(f => f.path);
    const comparedPaths = diff.files
      .filter(f => f.group === 'compared')
      .map(f => f.path);

    if (originalPaths.length === 0 || comparedPaths.length === 0) {
      alert('请至少为原件和比对件各导入一个文件。');
      return;
    }

    diff.setStep('processing');
    setOperationError(null);

    try {
      const origResult = await bridge.call('ocr.process_files', {
        files: originalPaths,
      });

      const compResult = await bridge.call('ocr.process_files', {
        files: comparedPaths,
      });

      diff.setOCRResults(origResult.pages, compResult.pages);

      // 收集 OCR 预览文本
      const ogrp: Record<string, { text: string; conf: number }> = {};
      for (const p of origResult.pages) {
        const key = p.source_file || '';
        if (!ogrp[key]) ogrp[key] = { text: '', conf: 0 };
        ogrp[key].text += (ogrp[key].text ? '\n' : '') + p.text;
        ogrp[key].conf = Math.max(ogrp[key].conf, p.confidence);
      }
      const cgrp: Record<string, { text: string; conf: number }> = {};
      for (const p of compResult.pages) {
        const key = p.source_file || '';
        if (!cgrp[key]) cgrp[key] = { text: '', conf: 0 };
        cgrp[key].text += (cgrp[key].text ? '\n' : '') + p.text;
        cgrp[key].conf = Math.max(cgrp[key].conf, p.confidence);
      }
      setOcrPreview({
        original: Object.entries(ogrp).map(([k, v]) => ({
          fileName: k.split(/[/\\]/).pop() || k, text: v.text, confidence: v.conf,
        })),
        compared: Object.entries(cgrp).map(([k, v]) => ({
          fileName: k.split(/[/\\]/).pop() || k, text: v.text, confidence: v.conf,
        })),
      });

      const diffResult = await bridge.call('diff.compare', {
        original_pages: origResult.pages,
        compared_pages: compResult.pages,
      });

      diff.setDiffResults(diffResult.records, diffResult.summary);
      setOperationError(null);
    } catch (err: any) {
      logger.error('Diff comparison failed', err);
      setOperationError(err.message || '比对失败');
      diff.setStep('import');
    }
  }, [diff.files, bridge]);

  const handleBackToImport = useCallback(() => {
    diff.setStep('import');
  }, []);

  // ── 渲染 ──────────────────────────────────────────────

  return (
    <div className="app-container">
      {/* 标题栏 */}
      <header className="app-header">
        <h1>📋 合同比对工具</h1>
        <div className="header-right">
          {bridge.initializing && !bridge.error && (
            <span className="backend-status loading">
              <span className="status-dot" />
              后端启动中...
            </span>
          )}
          {bridge.isReady && (
            <span className="backend-status ready">
              <span className="status-dot" />
              后端就绪
            </span>
          )}
          {bridge.error && (
            <div className="backend-error-block">
              <span className="backend-status error" title={bridge.error}>
                <span className="status-dot" />
                后端未连接
              </span>
              <button className="btn-retry" onClick={bridge.retry}>
                🔄 重试
              </button>
            </div>
          )}
        </div>
      </header>

      {/* 后端错误详情 */}
      {bridge.error && (
        <div className="backend-error-banner">
          <p>
            <strong>⚠️ 后端服务未就绪</strong>
          </p>
          <p className="error-detail">{bridge.error}</p>
          <p className="error-hint">
            请确认：
            1) Python 3 已安装且已添加到系统 PATH；
            2) 依赖已安装（运行 pip install -r backend/requirements.txt）；
            3) 终端中可正常执行 python backend/server.py。
          </p>
        </div>
      )}

      {/* 主内容区 */}
      <main className="app-main">
        {diff.step === 'import' && (
          <>
            <FileImporter
              onFilesSelected={diff.addFiles}
            />
            <FileGroupList
              files={diff.files}
              onRemove={diff.removeFile}
              onChangeGroup={diff.changeFileGroup}
            />
            {diff.files.length > 0 && (
              <div className="actions-bar">
                <button
                  className="btn-primary"
                  onClick={handleStartCompare}
                  disabled={!bridge.isReady || bridge.isBusy}
                >
                  🔍 开始比对
                </button>
                <button className="btn-secondary" onClick={diff.clearFiles}>
                  清空文件
                </button>
              </div>
            )}
            {/* 操作错误提示（不影响后端连接状态） */}
            {operationError && (
              <div className="operation-error-banner">
                <button
                  className="btn-dismiss"
                  onClick={() => setOperationError(null)}
                >
                  ✕
                </button>
                <strong>⚠️ 比对失败</strong>
                <p className="error-detail">{operationError}</p>
              </div>
            )}
          </>
        )}

        {diff.step === 'processing' && (
          <ProcessingStatus
            progress={bridge.progress}
            isBusy={bridge.isBusy}
            error={bridge.error}
          />
        )}

        {diff.step === 'result' && (
          <>
            <DiffResultList
              records={diff.filteredRecords}
              summary={diff.diffSummary}
              activeFilter={diff.activeFilter}
              onFilterChange={diff.setActiveFilter}
              onBack={handleBackToImport}
            />
            <ExportButton
              records={diff.filteredRecords}
              summary={diff.diffSummary}
            />
            {/* OCR 识别文本预览 */}
            {ocrPreview && (
              <OcrPreviewPanel preview={ocrPreview} />
            )}
          </>
        )}
      </main>
    </div>
  );
};

export default App;
