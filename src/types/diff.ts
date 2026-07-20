/** 差异片段 — 字符级差异，含偏移量供前端精确高亮 */
export interface DiffFragment {
  type: 'replace' | 'delete' | 'insert';
  original: string;
  compared: string;
  originalStart: number;
  originalEnd: number;
  comparedStart: number;
  comparedEnd: number;
  /** OCR 置信度（0-1），< 0.8 时前端显示低置信度警告 */
  ocrConfidence?: number;
}

/** 单条差异记录 */
export interface DiffRecord {
  id: string;
  pageLabel: string;
  paragraphIndex: number;
  type: 'modified' | 'deleted' | 'added';
  originalText: string;
  comparedText: string;
  confidence: number;
  summary: string;
  fragments: DiffFragment[];
}

/** 比对的统计摘要 */
export interface DiffSummary {
  total: number;
  modified: number;
  deleted: number;
  added: number;
}

/** OCR 页面结果 */
export interface OCRPage {
  text: string;
  confidence: number;
  page_index: number;
  source_file: string;
  image_path: string | null;
  is_ocr: boolean;
}

/** 后端进度通知 */
export interface ProgressData {
  stage: 'ocr' | 'diff';
  current: number;
  total: number;
}

/** 文件分组 */
export type FileGroup = 'original' | 'compared';

/** 导入的文件 */
export interface FileEntry {
  id: string;
  path: string;
  name: string;
  group: FileGroup;
  ocrText?: string;        // OCR 识别文本（图片/PDF文件）
  ocrConfidence?: number;  // OCR 置信度
}
