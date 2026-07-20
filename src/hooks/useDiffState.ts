import { useState, useCallback } from 'react';
import type { DiffRecord, DiffSummary, OCRPage, FileEntry } from '../types/diff';

/**
 * 比对状态管理 Hook。
 *
 * 管理文件分组、OCR 结果、差异记录和应用状态流转。
 */
export type AppStep = 'import' | 'processing' | 'result';

export function useDiffState() {
  const [step, setStep] = useState<AppStep>('import');
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [originalPages, setOriginalPages] = useState<OCRPage[]>([]);
  const [comparedPages, setComparedPages] = useState<OCRPage[]>([]);
  const [diffRecords, setDiffRecords] = useState<DiffRecord[]>([]);
  const [diffSummary, setDiffSummary] = useState<DiffSummary | null>(null);
  const [activeFilter, setActiveFilter] = useState<string>('all');

  // 添加文件
  const addFiles = useCallback((paths: string[], group: 'original' | 'compared') => {
    const newFiles: FileEntry[] = paths.map((p, i) => ({
      id: `${group}-${Date.now()}-${i}`,
      path: p,
      name: p.split(/[/\\]/).pop() || p,
      group,
    }));
    setFiles(prev => [...prev, ...newFiles]);
  }, []);

  // 移除文件
  const removeFile = useCallback((id: string) => {
    setFiles(prev => prev.filter(f => f.id !== id));
  }, []);

  // 修改文件分组
  const changeFileGroup = useCallback((id: string, group: 'original' | 'compared') => {
    setFiles(prev => prev.map(f => f.id === id ? { ...f, group } : f));
  }, []);

  // 清空文件
  const clearFiles = useCallback(() => {
    setFiles([]);
    setOriginalPages([]);
    setComparedPages([]);
    setDiffRecords([]);
    setDiffSummary(null);
    setStep('import');
  }, []);

  // 设置处理结果
  const setOCRResults = useCallback((original: OCRPage[], compared: OCRPage[]) => {
    setOriginalPages(original);
    setComparedPages(compared);
  }, []);

  // 设置比对结果
  const setDiffResults = useCallback((records: DiffRecord[], summary: DiffSummary) => {
    setDiffRecords(records);
    setDiffSummary(summary);
    setStep('result');
  }, []);

  // 筛选后的差异记录
  const filteredRecords = activeFilter === 'all'
    ? diffRecords
    : diffRecords.filter(r => r.type === activeFilter);

  return {
    step,
    setStep,
    files,
    addFiles,
    removeFile,
    changeFileGroup,
    clearFiles,
    originalPages,
    comparedPages,
    setOCRResults,
    diffRecords,
    diffSummary,
    setDiffResults,
    activeFilter,
    setActiveFilter,
    filteredRecords,
  };
}
