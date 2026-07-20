import { useState, useEffect, useCallback, useRef } from 'react';
import type { ProgressData } from '../types/diff';

interface BridgeState {
  isReady: boolean;
  isBusy: boolean;
  error: string | null;
  progress: ProgressData | null;
  initializing: boolean;
}

/**
 * Python 后端通信 Hook。
 *
 * 封装与 Python 后端的 JSON-RPC 调用、进度监听和错误处理。
 * 提供 retry() 方法用于后端启动失败后重试。
 */
export function usePythonBridge() {
  const [state, setState] = useState<BridgeState>({
    isReady: false,
    isBusy: false,
    error: null,
    progress: null,
    initializing: true,
  });
  const cleanupRef = useRef<(() => void) | null>(null);

  const setupListeners = useCallback(() => {
    const api = window.electronAPI;
    if (!api) {
      setState(s => ({ ...s, error: 'Electron API 不可用，请确认在 Electron 环境中运行', initializing: false }));
      return () => {};
    }

    // 监听后端就绪（换成 on，含清理函数）
    const unsubReady = api.onBackendReady(() => {
      setState(s => ({ ...s, isReady: true, error: null, initializing: false }));
    });

    // 监听进度
    const unsubProgress = api.onBackendProgress((data: ProgressData) => {
      setState(s => ({ ...s, progress: data }));
    });

    // 监听错误
    const unsubError = api.onBackendError((error: any) => {
      setState(s => ({
        ...s,
        error: error.message || '后端错误',
        isBusy: false,
        isReady: false,
        initializing: false,
      }));
    });

    // 监听退出
    const unsubExited = api.onBackendExited((data: any) => {
      setState(s => ({
        ...s,
        isReady: false,
        initializing: false,
        error: `Python 后端进程已退出 (code=${data.code})`,
      }));
    });

    // 主动查询：后端可能已经就绪（解决竞态条件）
    api.getBackendStatus().then(status => {
      if (status.ready) {
        setState(s => ({ ...s, isReady: true, error: null, initializing: false }));
      }
    }).catch(() => {});

    return () => {
      unsubReady();
      unsubProgress();
      unsubError();
      unsubExited();
    };
  }, []);

  useEffect(() => {
    cleanupRef.current = setupListeners();
    return () => {
      cleanupRef.current?.();
    };
  }, [setupListeners]);

  /** 重新尝试连接后端 */
  const retry = useCallback(() => {
    setState(s => ({
      ...s,
      isReady: false,
      error: null,
      initializing: true,
      isBusy: false,
    }));
    // 重新注册监听器（onBackendReady 使用 once，需要重新绑定）
    cleanupRef.current?.();
    cleanupRef.current = setupListeners();
    // 通知主进程重新启动后端
    window.electronAPI?.retryBackend().catch(() => {
      // 错误会通过 backend:error 事件反馈
    });
  }, [setupListeners]);

  const call = useCallback(async (method: string, params?: any) => {
    // 只在操作期间设置 isBusy，不碰 error（error 仅由后端挂掉事件触发）
    setState(s => ({ ...s, isBusy: true }));
    try {
      const result = await window.electronAPI.callBackend(method, params);
      setState(s => ({ ...s, isBusy: false }));
      return result;
    } catch (err: any) {
      // 操作失败 ≠ 后端挂了，不清除 isReady
      setState(s => ({ ...s, isBusy: false }));
      throw err;
    }
  }, []);

  return { ...state, call, retry };
}
