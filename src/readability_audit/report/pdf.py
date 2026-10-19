"""HTML -> PDF via WeasyPrint (paged media, no JS needed)."""
from __future__ import annotations

from pathlib import Path


def write_pdf(html: str, path: str | Path, base_url: str | None = None) -> Path:
    from weasyprint import HTML
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=base_url or ".").write_pdf(str(p))
    return p
