import React from 'react';
import type { ProgressData } from '../types/diff';

interface Props {
  progress: ProgressData | null;
  isBusy: boolean;
  error: string | null;
}

/**
 * 处理进度组件 — OCR / 比对进度展示。
 */
export const ProcessingStatus: React.FC<Props> = ({ progress, isBusy, error }) => {
  if (!isBusy && !error) return null;

  const stageLabel = progress?.stage === 'ocr' ? 'OCR 文字识别' : '文本比对';
  const percent = progress && progress.total > 0
    ? Math.round((progress.current / progress.total) * 100)
    : 0;

  return (
    <div className="processing-status">
      {error ? (
        <div className="processing-error">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
        </div>
      ) : (
        <div className="processing-info">
          <div className="progress-header">
            <span className="stage-label">{stageLabel}中...</span>
            <span className="progress-text">
              {progress ? `${progress.current} / ${progress.total}` : '准备中...'}
            </span>
          </div>
          <div className="progress-bar-track">
            <div
              className="progress-bar-fill"
              style={{ width: `${percent}%` }}
            />
          </div>
          {progress && (
            <p className="progress-hint">
              正在处理，请耐心等待。处理速度取决于文件大小和数量。
            </p>
          )}
        </div>
      )}
    </div>
  );
};
