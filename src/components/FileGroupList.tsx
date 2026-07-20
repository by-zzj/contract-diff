import React from 'react';
import type { FileEntry, FileGroup } from '../types/diff';

interface Props {
  files: FileEntry[];
  onRemove: (id: string) => void;
  onChangeGroup: (id: string, group: FileGroup) => void;
}

/**
 * 文件分组列表 — 展示已导入的文件，支持调整分组和删除。
 */
export const FileGroupList: React.FC<Props> = ({ files, onRemove, onChangeGroup }) => {
  const originalFiles = files.filter(f => f.group === 'original');
  const comparedFiles = files.filter(f => f.group === 'compared');

  if (files.length === 0) return null;

  return (
    <div className="file-group-list">
      <div className="group-column">
        <div className="group-header original-header">
          <span className="group-badge original-badge">原件</span>
          <span className="group-count">{originalFiles.length} 个文件</span>
        </div>
        {originalFiles.map(f => (
          <FileItem
            key={f.id}
            file={f}
            onRemove={onRemove}
            onChangeGroup={onChangeGroup}
          />
        ))}
        {originalFiles.length === 0 && (
          <div className="empty-group">尚未导入原件</div>
        )}
      </div>

      <div className="group-column">
        <div className="group-header compared-header">
          <span className="group-badge compared-badge">比对件</span>
          <span className="group-count">{comparedFiles.length} 个文件</span>
        </div>
        {comparedFiles.map(f => (
          <FileItem
            key={f.id}
            file={f}
            onRemove={onRemove}
            onChangeGroup={onChangeGroup}
          />
        ))}
        {comparedFiles.length === 0 && (
          <div className="empty-group">尚未导入比对件</div>
        )}
      </div>
    </div>
  );
};

/** 单个文件条目 */
const FileItem: React.FC<{
  file: FileEntry;
  onRemove: (id: string) => void;
  onChangeGroup: (id: string, group: FileGroup) => void;
}> = ({ file, onRemove, onChangeGroup }) => {
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  const isImage = ['jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'].includes(ext);
  const isPdf = ext === 'pdf';
  const isDoc = ['docx', 'doc'].includes(ext);

  const icon = isImage ? '🖼️' : isPdf ? '📕' : isDoc ? '📝' : '📎';

  return (
    <div className="file-item">
      <span className="file-icon">{icon}</span>
      <span className="file-name" title={file.path}>{file.name}</span>
      <button
        className="btn-switch-group"
        onClick={() => onChangeGroup(file.id, file.group === 'original' ? 'compared' : 'original')}
        title="切换到另一组"
      >
        ⇄
      </button>
      <button
        className="btn-remove-file"
        onClick={() => onRemove(file.id)}
        title="移除"
      >
        ✕
      </button>
    </div>
  );
};
