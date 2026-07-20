import { app, BrowserWindow, ipcMain, dialog, Menu } from 'electron';
import path from 'path';
import fs from 'fs';
import { PythonBridge } from './python-bridge';

// 移除默认英文菜单栏（本工具所有操作通过界面按钮完成）
Menu.setApplicationMenu(null);

let mainWindow: BrowserWindow | null = null;
let pythonBridge: PythonBridge | null = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    title: '合同比对工具',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // 开发模式加载 Vite dev server
  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ── Python Bridge 管理 ──────────────────────────────────

async function initPythonBridge() {
  pythonBridge = new PythonBridge();

  pythonBridge.on('progress', (data) => {
    mainWindow?.webContents.send('backend:progress', data);
  });

  pythonBridge.on('error', (err) => {
    mainWindow?.webContents.send('backend:error', err);
  });

  pythonBridge.on('exited', (code) => {
    mainWindow?.webContents.send('backend:exited', { code });
  });

  try {
    await pythonBridge.start();
    mainWindow?.webContents.send('backend:ready');
  } catch (err: any) {
    console.error('Python 后端启动失败:', err.message);
    mainWindow?.webContents.send('backend:error', {
      message: `Python 后端启动失败: ${err.message}`,
    });
  }
}

// ── IPC 处理 ────────────────────────────────────────────

function setupIPC() {
  // 转发前端请求到 Python 后端
  ipcMain.handle('backend:call', async (_event, method: string, params: any) => {
    if (!pythonBridge || !pythonBridge.isRunning) {
      throw new Error('Python 后端未就绪，请点击右上角"重试"按钮');
    }
    return pythonBridge.call(method, params);
  });

  // 重新启动 Python 后端
  ipcMain.handle('backend:retry', async () => {
    pythonBridge?.stop();
    pythonBridge = null;
    await initPythonBridge();
    return pythonBridge?.isRunning ?? false;
  });

  // 打开文件对话框
  ipcMain.handle('dialog:openFiles', async (_event, options: any) => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      title: '选择合同文件',
      filters: [
        {
          name: '支持的文件',
          extensions: ['pdf', 'docx', 'doc', 'jpg', 'jpeg', 'png', 'bmp', 'tiff', 'tif', 'webp'],
        },
        { name: '所有文件', extensions: ['*'] },
      ],
      properties: ['openFile', 'multiSelections'],
      ...options,
    });
    return result.filePaths;
  });

  // 保存文件对话框
  ipcMain.handle('dialog:saveFile', async (_event, options: {
    defaultPath: string;
    content: string;
    encoding?: string;
  }) => {
    const result = await dialog.showSaveDialog(mainWindow!, {
      title: '保存文件',
      defaultPath: options.defaultPath,
      filters: [
        { name: 'HTML 报告', extensions: ['html'] },
        { name: 'CSV 文件', extensions: ['csv'] },
        { name: '所有文件', extensions: ['*'] },
      ],
    });

    if (result.canceled || !result.filePath) {
      return null;
    }

    fs.writeFileSync(result.filePath, options.content, {
      encoding: (options.encoding || 'utf-8') as BufferEncoding,
    });

    return result.filePath;
  });

  // 获取文件信息
  ipcMain.handle('app:getPath', async (_event, name: string) => {
    return app.getPath(name as any);
  });
}

// ── 应用生命周期 ────────────────────────────────────────

app.whenReady().then(async () => {
  setupIPC();
  createWindow();
  await initPythonBridge();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  pythonBridge?.stop();
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  pythonBridge?.stop();
});
