import { contextBridge, ipcRenderer } from 'electron';

/**
 * 向渲染进程暴露的安全 API。
 * 使用 contextBridge 隔离，防止渲染进程直接访问 Node.js API。
 */
contextBridge.exposeInMainWorld('electronAPI', {
  // ── 后端通信 ──────────────────────────────────────

  /** 调用 Python 后端方法 */
  callBackend: (method: string, params?: any): Promise<any> => {
    return ipcRenderer.invoke('backend:call', method, params);
  },

  /** 重新启动 Python 后端 */
  retryBackend: (): Promise<boolean> => {
    return ipcRenderer.invoke('backend:retry');
  },

  /** 监听后端进度通知 */
  onBackendProgress: (callback: (data: any) => void) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on('backend:progress', handler);
    return () => ipcRenderer.removeListener('backend:progress', handler);
  },

  /** 监听后端就绪 */
  onBackendReady: (callback: () => void) => {
    ipcRenderer.once('backend:ready', () => callback());
  },

  /** 监听后端错误 */
  onBackendError: (callback: (error: any) => void) => {
    const handler = (_event: any, error: any) => callback(error);
    ipcRenderer.on('backend:error', handler);
    return () => ipcRenderer.removeListener('backend:error', handler);
  },

  /** 监听后端退出 */
  onBackendExited: (callback: (data: any) => void) => {
    const handler = (_event: any, data: any) => callback(data);
    ipcRenderer.on('backend:exited', handler);
    return () => ipcRenderer.removeListener('backend:exited', handler);
  },

  // ── 文件对话框 ────────────────────────────────────

  /** 打开文件选择对话框 */
  openFileDialog: (options?: any): Promise<string[]> => {
    return ipcRenderer.invoke('dialog:openFiles', options);
  },

  /** 打开保存文件对话框并写入内容 */
  saveFileDialog: (options: { defaultPath: string; content: string; encoding?: string }): Promise<string | null> => {
    return ipcRenderer.invoke('dialog:saveFile', options);
  },

  // ── 应用信息 ──────────────────────────────────────

  /** 获取应用路径 */
  getPath: (name: string): Promise<string> => {
    return ipcRenderer.invoke('app:getPath', name);
  },
});
