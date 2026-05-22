from __future__ import annotations

from io import BytesIO


def extract_pdf_text(pdf_bytes: bytes, max_chars: int = 8000) -> str:
    if not pdf_bytes:
        return ""

    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception:
        return ""

    parts: list[str] = []
    total = 0
    limit = max(1, max_chars)

    for page in reader.pages:
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if not text:
            continue
        remain = limit - total
        if remain <= 0:
            break
        if len(text) > remain:
            text = text[:remain]
        parts.append(text)
        total += len(text)
        if total >= limit:
            break

    return "\n\n".join(parts).strip()


def extract_pdf_title(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        return ""

    try:
        from pypdf import PdfReader
    except Exception:
        return ""

    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception:
        return ""

    # 1) Metadata title first.
    try:
        meta = reader.metadata or {}
        title = str(meta.get("/Title") or "").strip()
        if title:
            return title
    except Exception:
        pass

    # 2) Fallback to first non-empty line of first pages.
    for page in reader.pages[:3]:
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if not text:
            continue
        for line in text.splitlines():
            line = line.strip()
            if len(line) >= 4:
                return line[:120]
    return ""
