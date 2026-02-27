"""论文处理服务 — 文件保存、文本提取。"""

import uuid
from pathlib import Path

from app.config import UPLOAD_DIR


def save_upload(filename: str, content: bytes) -> str:
    """保存上传的文件，返回文件路径。"""
    suffix = Path(filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    file_path = UPLOAD_DIR / unique_name
    file_path.write_bytes(content)
    return str(file_path)


def extract_text(file_path: str) -> str:
    """从文件中提取文本内容。支持 PDF 和 Markdown/文本文件。"""
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf_text(path)
    elif suffix in (".md", ".txt", ".tex"):
        return path.read_text(encoding="utf-8", errors="ignore")
    else:
        # 尝试作为文本读取
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return "[Unable to extract text from this file format]"


def _extract_pdf_text(path: Path) -> str:
    """使用PyMuPDF从PDF提取文本。"""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(path))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except ImportError:
        return "[PyMuPDF not installed — cannot extract PDF text]"
    except Exception as e:
        return f"[PDF extraction error: {e}]"
