import { spawn, ChildProcess } from 'child_process';
import path from 'path';
import fs from 'fs';
import os from 'os';
import { app } from 'electron';
import EventEmitter from 'events';

// ── 主进程日志 ────────────────────────────────────────────
const LOG_DIR = path.join(os.homedir(), '.contract-diff', 'logs');
fs.mkdirSync(LOG_DIR, { recursive: true });
const LOG_FILE = path.join(LOG_DIR, 'electron.log');

function logMain(level: string, msg: string) {
  const line = `[${new Date().toISOString()}] [${level}] ${msg}\n`;
  fs.appendFileSync(LOG_FILE, line);
  if (level === 'ERROR') console.error(msg);
  else console.log(msg);
}

interface RPCRequest {
  id: number;
  method: string;
  params: any;
}

interface RPCResponse {
  id: number;
  result?: any;
  error?: { code: number; message: string };
}

/**
 * Python 后端进程管理 + JSON-RPC 通信。
 *
 * 架构:
 *   Electron main → spawn backend.exe → stdin/stdout JSON-RPC
 *
 * 进度通知（服务器推送）:
 *   Python 可以直接写 {type: "progress", ...} 到 stdout，
 *   Bridge 识别并 emit 'progress' 事件。
 */
export class PythonBridge extends EventEmitter {
  private process: ChildProcess | null = null;
  private requestId = 0;
  private pending = new Map<number, { resolve: Function; reject: Function }>();
  private buffer = '';

  get isRunning(): boolean {
    return this.process !== null && !this.process.killed;
  }

  async start(): Promise<void> {
    const isPackaged = app.isPackaged;
    const baseDir = isPackaged ? process.resourcesPath : app.getAppPath();
    const backendPyPath = path.join(baseDir, 'backend', 'server.py');

    // 策略：venv Python > backend.exe > 系统 python3
    const venvPython = path.join(baseDir, 'backend', 'venv', 'Scripts', 'python.exe');
    const exePath = path.join(baseDir, 'backend', 'backend.exe');

    if (fs.existsSync(venvPython)) {
      // PaddleOCR 完整版（Python 3.11 venv，含 PaddlePaddle + PP-OCRv4 模型）
      logMain('INFO', 'OCR 引擎: PaddleOCR (venv Python 3.11)');
      this.process = spawn(venvPython, [backendPyPath], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONUNBUFFERED: '1' },
      });
    } else if (fs.existsSync(exePath)) {
      logMain('INFO', '使用 backend.exe: ' + exePath);
      this.process = spawn(exePath, [], {
        stdio: ['pipe', 'pipe', 'pipe'],
      });
    } else if (!isPackaged) {
      const pythonCmd = 'python3';
      logMain('INFO', '使用系统 Python: ' + pythonCmd + ' -> ' + backendPyPath);
      this.process = spawn(pythonCmd, [backendPyPath], {
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONUNBUFFERED: '1' },
      });
    } else {
      throw new Error('找不到 Python 运行环境，请重新安装应用程序');
    }

    // stdout — JSON-RPC 响应 + 服务器推送
    this.process.stdout?.on('data', (chunk: Buffer) => {
      this.buffer += chunk.toString('utf-8');
      const lines = this.buffer.split('\n');
      this.buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const data = JSON.parse(line);

          // 服务器推送（进度通知）
          if (data.type === 'progress') {
            this.emit('progress', data);
            continue;
          }

          // JSON-RPC 响应
          this._handleResponse(data);
        } catch {
          // 非 JSON 输出，可能是日志
          console.log('[python]', line);
        }
      }
    });

    // stderr — 日志输出（也写入日志文件）
    this.process.stderr?.on('data', (chunk: Buffer) => {
      const msg = chunk.toString('utf-8').trim();
      logMain('INFO', `[python] ${msg}`);
    });

    // 进程启动失败（如 python 命令不存在）
    this.process.on('error', (err) => {
      logMain('ERROR', `Python 进程错误: ${(err as any).code === 'ENOENT'
        ? '未找到 Python，请确认已安装 Python 3 并添加到 PATH'
        : err.message}`);
      const errMsg = (err as any).code === 'ENOENT'
        ? '未找到 Python，请确认已安装 Python 3 并添加到 PATH 环境变量'
        : `Python 进程错误: ${err.message}`;
      this.emit('error', { message: errMsg });
    });

    this.process.on('exit', (code) => {
      const msg = `Python 进程退出, code=${code}`;
      logMain(code === 0 ? 'INFO' : 'ERROR', msg);
      this.process = null;
      for (const [id, { reject }] of this.pending) {
        reject(new Error(`Python 后端进程已退出 (code=${code})`));
        this.pending.delete(id);
      }
      this.emit('exited', code);
    });

    // 等待就绪信号（启动阶段使用较短超时）
    try {
      await this._callWithTimeout('health.ping', {}, 15000);
    } catch (err: any) {
      // 启动失败，清理进程
      this.stop();
      throw err;
    }
  }

  /**
   * 带自定义超时的 RPC 调用（用于启动阶段）。
   */
  private _callWithTimeout(method: string, params: any, timeoutMs: number): Promise<any> {
    return new Promise((resolve, reject) => {
      const id = ++this.requestId;
      const request: RPCRequest = { id, method, params };

      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(
          `后端启动超时 (${timeoutMs / 1000}s)。` +
          '请确认 Python 已安装且 paddleocr 等依赖已配置。'
        ));
      }, timeoutMs);

      const wrappedResolve = (result: any) => {
        clearTimeout(timer);
        resolve(result);
      };
      const wrappedReject = (err: any) => {
        clearTimeout(timer);
        reject(err);
      };
      this.pending.set(id, { resolve: wrappedResolve, reject: wrappedReject });

      const line = JSON.stringify(request) + '\n';
      this.process?.stdin?.write(line);
    });
  }

  /**
   * 调用 Python 后端方法。
   */
  call(method: string, params: any = {}): Promise<any> {
    return new Promise((resolve, reject) => {
      const id = ++this.requestId;
      const request: RPCRequest = { id, method, params };

      // 设置超时（OCR 可能需要较长时间）
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`请求超时: ${method}`));
      }, 300000); // 5 分钟

      this.pending.set(id, { resolve, reject });
      const wrappedResolve = (result: any) => {
        clearTimeout(timeout);
        resolve(result);
      };
      const wrappedReject = (err: any) => {
        clearTimeout(timeout);
        reject(err);
      };
      this.pending.set(id, { resolve: wrappedResolve, reject: wrappedReject });

      const line = JSON.stringify(request) + '\n';
      this.process?.stdin?.write(line);
    });
  }

  stop(): void {
    if (this.process) {
      this.process.stdin?.end();
      this.process.kill();
      this.process = null;
    }
  }

  private _handleResponse(data: RPCResponse): void {
    const pending = this.pending.get(data.id);
    if (!pending) return;

    this.pending.delete(data.id);

    if (data.error) {
      pending.reject(new Error(data.error.message));
    } else {
      pending.resolve(data.result);
    }
  }
}
