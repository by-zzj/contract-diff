/**
 * 结构化日志工具。
 *
 * 开发模式通过 console 输出，生产模式静默缓冲。
 * 替换所有 console.log/console.error 调用。
 */

type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  message: string;
  data?: unknown;
}

const buffer: LogEntry[] = [];
const MAX_BUFFER = 100;

function createLogger() {
  function log(level: LogLevel, message: string, data?: unknown): void {
    const entry: LogEntry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      ...(data !== undefined ? { data } : {}),
    };

    // 生产模式静默，开发模式输出
    if (import.meta.env.DEV) {
      const fn =
        level === 'error' ? console.error
        : level === 'warn' ? console.warn
        : console.log;
      fn(`[${entry.timestamp}] [${level.toUpperCase()}] ${message}`, data ?? '');
    }

    if (buffer.length >= MAX_BUFFER) {
      buffer.shift();
    }
    buffer.push(entry);
  }

  return {
    debug: (message: string, data?: unknown) => log('debug', message, data),
    info: (message: string, data?: unknown) => log('info', message, data),
    warn: (message: string, data?: unknown) => log('warn', message, data),
    error: (message: string, data?: unknown) => log('error', message, data),
    getBuffer: (): LogEntry[] => [...buffer],
  };
}

export const logger = createLogger();
