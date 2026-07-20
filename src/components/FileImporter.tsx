import { useCallback } from 'react';
import { logger } from '../utils/logger';

interface Props {
  onFilesSelected: (paths: string[], group: 'original' | 'compared') => void;
  disabled?: boolean;
}

/**
 * 文件导入组件 — 支持拖拽和点击选择。
 */
export const FileImporter: React.FC<Props> = ({ onFilesSelected, disabled }) => {
  const handleClick = useCallback(async (group: 'original' | 'compared') => {
    try {
      const paths = await window.electronAPI.openFileDialog();
      if (paths.length > 0) {
        onFilesSelected(paths, group);
      }
    } catch (err: any) {
      logger.error('File selection failed', err);
    }
  }, [onFilesSelected]);

  const handleDrop = useCallback((e: React.DragEvent, group: 'original' | 'compared') => {
    e.preventDefault();
    if (disabled) return;

    const paths: string[] = [];
    for (const file of e.dataTransfer.files) {
      // 在 Electron 中，文件的 path 属性可用
      const filePath = (file as any).path;
      if (filePath) {
        paths.push(filePath);
      }
    }
    if (paths.length > 0) {
      onFilesSelected(paths, group);
    }
  }, [onFilesSelected, disabled]);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  return (
    <div className="file-importer">
      <div className="import-columns">
        {/* 原件导入区 */}
        <div
          className={`import-zone original-zone ${disabled ? 'disabled' : ''}`}
          onDrop={(e) => handleDrop(e, 'original')}
          onDragOver={handleDragOver}
          onClick={() => !disabled && handleClick('original')}
        >
          <div className="zone-icon">📄</div>
          <h3>原件</h3>
          <p>拖拽或点击导入</p>
          <p className="zone-hint">原始合同文件（PDF / Word / 图片）</p>
        </div>

        {/* 比对件导入区 */}
        <div
          className={`import-zone compared-zone ${disabled ? 'disabled' : ''}`}
          onDrop={(e) => handleDrop(e, 'compared')}
          onDragOver={handleDragOver}
          onClick={() => !disabled && handleClick('compared')}
        >
          <div className="zone-icon">📑</div>
          <h3>比对件</h3>
          <p>拖拽或点击导入</p>
          <p className="zone-hint">实际签署的扫描件（图片 / PDF）</p>
        </div>
      </div>
    </div>
  );
};
