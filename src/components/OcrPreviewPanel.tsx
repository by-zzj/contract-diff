import { useState } from 'react';

interface OcrFilePreview {
  fileName: string;
  text: string;
  confidence: number;
}

interface Props {
  preview: {
    original: OcrFilePreview[];
    compared: OcrFilePreview[];
  };
}

export const OcrPreviewPanel: React.FC<Props> = ({ preview }) => {
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <div className="ocr-preview-bar">
        <button className="btn-preview-open" onClick={() => setOpen(true)}>
          📝 查看识别文本
        </button>
      </div>
    );
  }

  const origItems = preview.original;
  const compItems = preview.compared;
  const maxItems = Math.max(origItems.length, compItems.length);

  const renderItems = (items: OcrFilePreview[]) =>
    items.length === 0 ? (
      <p className="ocr-empty">无文本内容</p>
    ) : (
      items.map((item, i) => (
        <div key={i} className="ocr-file-block">
          <div className="ocr-file-meta">
            <span className="ocr-file-name">{item.fileName}</span>
            <span className="ocr-file-conf">
              OCR {(item.confidence * 100).toFixed(0)}% · {item.text.length} 字
            </span>
          </div>
          <div className="ocr-file-text">{item.text}</div>
        </div>
      ))
    );

  return (
    <div className="ocr-modal-overlay" onClick={() => setOpen(false)}>
      <div className="ocr-modal" onClick={e => e.stopPropagation()}>
        <div className="ocr-modal-header">
          <h2>📝 识别文本对比预览</h2>
          <button className="ocr-modal-close" onClick={() => setOpen(false)}>✕</button>
        </div>
        <div className="ocr-modal-body ocr-split-body">
          <div className="ocr-column">
            <div className="ocr-col-header">原件</div>
            <div className="ocr-col-content">{renderItems(origItems)}</div>
          </div>
          <div className="ocr-column">
            <div className="ocr-col-header comp">比对件</div>
            <div className="ocr-col-content">{renderItems(compItems)}</div>
          </div>
        </div>
      </div>
    </div>
  );
};
