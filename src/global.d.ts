/// <reference types="vite/client" />

export {};

declare global {
  interface Window {
    electronAPI: {
      callBackend: (method: string, params?: any) => Promise<any>;
      retryBackend: () => Promise<boolean>;
      onBackendProgress: (callback: (data: any) => void) => () => void;
      onBackendReady: (callback: () => void) => () => void;
      getBackendStatus: () => Promise<{ ready: boolean }>;
      onBackendError: (callback: (error: any) => void) => () => void;
      onBackendExited: (callback: (data: any) => void) => () => void;
      openFileDialog: (options?: any) => Promise<string[]>;
      saveFileDialog: (options: { defaultPath: string; content: string; encoding?: string }) => Promise<string | null>;
      getPath: (name: string) => Promise<string>;
    };
  }
}
