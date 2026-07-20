"""
Contract Diff — Python 后端服务。

stdio JSON-RPC 服务，由 Electron 主进程通过 child_process spawn 启动，
通过 stdin/stdout 与前端通信。
"""

import io
import json
import sys
import os
import logging
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

# ── 强制 UTF-8 编码（修复 PyInstaller 打包后中文路径乱码） ─
if hasattr(sys.stdin, 'buffer'):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# ── 日志配置（stderr + 文件双写）─────────────────────────
LOG_DIR = Path(os.environ.get("CONTRACT_DIFF_LOG_DIR", Path.home() / ".contract-diff" / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "backend.log"

# 文件 handler（errors='replace' 防止乱码导致日志崩溃）
file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8", errors="replace")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
))

# stderr handler（同样防乱码）
stderr_handler = logging.StreamHandler(sys.stderr)
stderr_handler.setLevel(logging.INFO)
stderr_handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))

# 根 logger
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG)
root_logger.addHandler(file_handler)
root_logger.addHandler(stderr_handler)

logger = logging.getLogger("contract-diff")
logger.info(f"日志文件: {LOG_FILE}")

# ── 延迟导入（加快启动，按需加载）───────────────────────

_engine = None
_parsers_cache = {}


def _get_engine():
    global _engine
    if _engine is None:
        # 自动检测最佳可用引擎：PaddleOCR > EasyOCR > Tesseract > Demo
        # 1. PaddleOCR（中文准确率最高 97%+，PP-OCRv4）
        try:
            from ocr.engine import OCREngine
            _engine = OCREngine.get_instance()
            logger.info("OCR 引擎: PaddleOCR (PP-OCRv4, 中文 97%+)")
            return _engine
        except Exception as e:
            logger.info(f"PaddleOCR 不可用: {e}")

        # 2. EasyOCR（PyTorch 备选，中文 ~95%）
        try:
            from ocr.easyocr_engine import EasyOCREngine
            _engine = EasyOCREngine.get_instance()
            logger.info("OCR 引擎: EasyOCR (PyTorch)")
            return _engine
        except Exception as e:
            logger.info(f"EasyOCR 不可用: {e}")

        # 3. Tesseract（需要独立安装程序）
        try:
            from ocr.tesseract_engine import TesseractEngine
            eng = TesseractEngine.get_instance()
            if eng.is_ready:
                _engine = eng
                logger.info("OCR 引擎: Tesseract")
                return _engine
        except Exception as e:
            logger.info(f"Tesseract 不可用: {e}")

        # 4. Demo（纯文本提取，仅限 Word/PDF）
        from ocr.demo_engine import DemoOCREngine
        _engine = DemoOCREngine.get_instance()
        logger.warning("OCR 引擎: Demo（图片识别需安装 PaddleOCR）")
    return _engine


# ── RPC 方法注册表 ───────────────────────────────────────

_METHODS: dict[str, Callable] = {}


def method(name: str):
    """装饰器：注册 JSON-RPC 方法。"""
    def decorator(fn: Callable):
        _METHODS[name] = fn
        return fn
    return decorator


# ── RPC 方法实现 ─────────────────────────────────────────


@method("health.ping")
def handle_ping(params: dict) -> dict:
    """心跳检测。"""
    return {"status": "ok", "version": "1.0.0"}


@method("ocr.recognize")
def handle_ocr(params: dict) -> dict:
    """
    对图片文件执行 OCR 识别。

    params:
        files: [str] — 图片文件路径列表
        dpi: int — 图片 DPI（默认 150）

    returns:
        {pages: [{text, confidence, page_index, quality}]}
    """
    files = params.get("files", [])
    dpi = params.get("dpi", 150)

    if not files:
        raise ValueError("files 不能为空")

    engine = _get_engine()

    send_progress("ocr", 0, len(files))

    results = engine.recognize_batch(
        files,
        dpi=dpi,
        on_progress=lambda cur, total: send_progress("ocr", cur, total),
    )

    pages = []
    for r in results:
        pages.append({
            "text": r.text,
            "confidence": round(r.confidence, 3),
            "page_index": r.page_index,
            "quality": {
                "dpi": r.quality.dpi if r.quality else 150,
                "is_low_quality": r.quality.is_low_quality if r.quality else False,
            } if r.quality else None,
        })

    return {"pages": pages}


@method("ocr.process_files")
def handle_process_files(params: dict) -> dict:
    """
    解析文件 + OCR 识别（一站式处理）。

    params:
        files: [str] — 文件路径列表（支持 PDF/Word/图片）

    returns:
        {pages: [{text, confidence, page_index, source_file, image_path}]}
    """
    files = params.get("files", [])
    if not files:
        raise ValueError("files 不能为空")

    from parser.base import BaseParser
    engine = _get_engine()

    all_pages = []

    for file_path in files:
        parser = BaseParser.get_parser(file_path)
        parsed = parser.parse(file_path)

        for page in parsed:
            if page.image_path:
                # 扫描型 → OCR
                send_progress("ocr", len(all_pages) + 1, len(files) * 10)
                result = engine.recognize(
                    image_path=page.image_path,
                    page_index=page.page_index,
                )
                all_pages.append({
                    "text": result.text,
                    "confidence": round(result.confidence, 3),
                    "page_index": page.page_index,
                    "source_file": page.source_file,
                    "image_path": page.image_path,
                    "is_ocr": True,
                })
            elif page.raw_text:
                # 文字型 → 直接使用
                all_pages.append({
                    "text": page.raw_text,
                    "confidence": 1.0,
                    "page_index": page.page_index,
                    "source_file": page.source_file,
                    "image_path": None,
                    "is_ocr": False,
                })

    return {"pages": all_pages}


@method("diff.compare")
def handle_diff(params: dict) -> dict:
    """
    对两组文本执行差异比对。

    params:
        original_pages: [{text, page_index, ...}] — 原件页面列表
        compared_pages: [{text, page_index, ...}] — 比对件页面列表

    returns:
        {records: [DiffRecord], summary: {total, modified, deleted, added}}
    """
    original_pages = params.get("original_pages", [])
    compared_pages = params.get("compared_pages", [])

    if not original_pages and not compared_pages:
        return {"records": [], "summary": {"total": 0, "modified": 0, "deleted": 0, "added": 0}}

    # 拼接全文
    orig_text = "\n\n".join(p.get("text", "") for p in original_pages)
    comp_text = "\n\n".join(p.get("text", "") for p in compared_pages)

    # 取最低置信度
    orig_conf = min((p.get("confidence", 0.95) for p in original_pages), default=0.95)
    comp_conf = min((p.get("confidence", 0.95) for p in compared_pages), default=0.95)
    base_conf = min(orig_conf, comp_conf)

    from comparator.differ import compare
    records = compare(
        original_text=orig_text,
        compared_text=comp_text,
        page_label="全文比对",
        base_confidence=base_conf,
    )

    # 转 dict
    records_data = []
    for r in records:
        records_data.append({
            "id": r.id,
            "pageLabel": r.page_label,
            "paragraphIndex": r.paragraph_index,
            "type": r.type,
            "originalText": r.original_text,
            "comparedText": r.compared_text,
            "confidence": r.confidence,
            "summary": r.summary,
            "fragments": [
                {
                    "type": f.type,
                    "original": f.original,
                    "compared": f.compared,
                    "originalStart": getattr(f, 'original_start', 0),
                    "originalEnd": getattr(f, 'original_end', 0),
                    "comparedStart": getattr(f, 'compared_start', 0),
                    "comparedEnd": getattr(f, 'compared_end', 0),
                }
                for f in r.fragments
            ],
        })

    summary = {
        "total": len(records),
        "modified": sum(1 for r in records if r.type == "modified"),
        "deleted": sum(1 for r in records if r.type == "deleted"),
        "added": sum(1 for r in records if r.type == "added"),
    }

    return {"records": records_data, "summary": summary}


# ── JSON-RPC 通信层 ──────────────────────────────────────


def send_progress(stage: str, current: int, total: int):
    """发送进度通知到 Electron（服务器推送）。"""
    notification = {
        "type": "progress",
        "stage": stage,
        "current": current,
        "total": total,
    }
    _write_response(notification)


def _write_response(data: dict):
    """向 stdout 写入一行 JSON（UTF-8 安全）。"""
    try:
        line = json.dumps(data, ensure_ascii=False) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()
    except Exception:
        # 极端情况：data 含不可编码字符，用 ensure_ascii=True 兜底
        line = json.dumps(data, ensure_ascii=True) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()


def _read_request() -> Optional[dict]:
    """从 stdin 读取一行 JSON 请求。"""
    try:
        line = sys.stdin.readline()
        if not line:
            return None  # EOF — 父进程关闭了 stdin
        return json.loads(line.strip())
    except json.JSONDecodeError as e:
        logger.error(f"JSON 解析失败: {e}")
        return None
    except Exception as e:
        logger.error(f"读取请求失败: {e}")
        return None


def _handle_request(request: dict):
    """处理单个 JSON-RPC 请求。"""
    req_id = request.get("id")
    method_name = request.get("method", "")
    params = request.get("params", {})

    fn = _METHODS.get(method_name)
    if fn is None:
        _write_response({
            "id": req_id,
            "error": {"code": -32601, "message": f"未知方法: {method_name}"},
        })
        return

    try:
        result = fn(params)
        _write_response({
            "id": req_id,
            "result": result,
        })
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"方法 {method_name} 执行失败:\n{tb}")
        _write_response({
            "id": req_id,
            "error": {"code": -1, "message": f"{type(e).__name__}: {e}"},
        })


# ── 主循环 ───────────────────────────────────────────────


def main():
    """stdio JSON-RPC 主循环。"""
    logger.info("Contract Diff 后端服务启动")

    # 注册信号：通过 stdin 读到的第一条消息开始工作
    # 持续等待请求
    while True:
        request = _read_request()
        if request is None:
            logger.info("stdin 已关闭，服务退出")
            break
        _handle_request(request)


if __name__ == "__main__":
    main()
