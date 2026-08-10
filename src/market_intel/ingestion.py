from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import pandas as pd
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from docx import Document

from .config import get_settings
from .security import validate_public_url


def _clip(text: str) -> str:
    limit = int(get_settings().section("analysis")["max_news_characters"])
    return text.strip()[:limit]


def read_url(url: str) -> tuple[str, str]:
    cfg = get_settings().section("security")
    current_url = validate_public_url(url)
    headers = {"User-Agent": get_settings().section("app")["name"]}
    session = requests.Session()

    for _ in range(int(cfg["max_redirects"]) + 1):
        response = session.get(
            current_url,
            timeout=cfg["url_timeout_seconds"],
            headers=headers,
            stream=True,
            allow_redirects=False,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("location")
            response.close()
            if not location:
                raise ValueError("Redirect response did not provide a target URL.")
            from urllib.parse import urljoin
            current_url = validate_public_url(urljoin(current_url, location))
            continue
        response.raise_for_status()
        break
    else:
        raise ValueError("URL exceeded the configured redirect limit.")

    with response:
        chunks, total = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > int(cfg["max_url_bytes"]):
                raise ValueError("Remote content exceeds configured size limit.")
            chunks.append(chunk)
        body = b"".join(chunks)
        content_type = response.headers.get("content-type", "").lower()

    if "pdf" in content_type or current_url.lower().endswith(".pdf"):
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(body)).pages)
    else:
        soup = BeautifulSoup(body, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
    if not text.strip():
        raise ValueError("No readable text found at URL.")
    return _clip(text), current_url


def read_uploaded_file(file_name: str, file_bytes: bytes) -> tuple[str, str]:
    suffix = Path(file_name).suffix.lower()
    if suffix == ".pdf":
        text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(file_bytes)).pages)
    elif suffix == ".docx":
        doc = Document(BytesIO(file_bytes))
        text = "\n".join(p.text for p in doc.paragraphs)
    elif suffix == ".csv":
        df = pd.read_csv(BytesIO(file_bytes))
        text = df.to_csv(index=False)
    elif suffix == ".json":
        text = json.dumps(json.loads(file_bytes.decode("utf-8")), indent=2)
    elif suffix in {".txt", ".md"}:
        text = file_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError("Unsupported file type. Use PDF, DOCX, CSV, JSON, TXT, or MD.")
    if not text.strip():
        raise ValueError("Uploaded file contains no readable text.")
    return _clip(text), file_name
