"""One embedding interface for the whole project.

    from embeddings import embed, embed_file, cosine

    doc_vecs = embed(["Wind gusts to 30 mph Thursday", "RFI #12: mullion spacing"])
    query_vec = embed("can we fly in high wind?", kind="query")[0]
    photo_vec = embed_file("site_photo.jpg")

Settings come from .env (see .env.example):
    EMBEDDING_PROVIDER   "local" (default) or "openrouter"
    EMBEDDING_MODEL      OpenRouter model id, default google/gemini-embedding-2
    EMBEDDING_DIMENSIONS default 768 (both providers support it)
    OPENROUTER_API_KEY   for provider=openrouter
    LOCAL_EMBEDDING_URL  for provider=local, e.g. http://10.70.4.24:8000
                         (from inside Docker on the host Mac: http://host.docker.internal:8000)
    LOCAL_EMBEDDING_KEY  for provider=local

Vectors from different providers/models live in different spaces and must never be
compared. Store `model_id()` next to every vector and only search within one model.
Returned vectors are L2-normalised, so cosine similarity is a dot product.

Standard library only, so it runs anywhere without extra installs.
"""

from __future__ import annotations

import base64
import json
import math
import mimetypes
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Literal, Sequence, Union

Kind = Literal["document", "query"]
OPENROUTER_URL = "https://openrouter.ai/api/v1/embeddings"
BATCH = 64


def _load_dotenv() -> None:
    """Read the repo-root .env into os.environ without overriding real env vars."""
    for parent in Path(__file__).resolve().parents:
        env = parent / ".env"
        if env.is_file():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return


_load_dotenv()


def _cfg(name: str, default: str | None = None) -> str:
    val = os.environ.get(name, default)
    if not val:
        raise RuntimeError(f"{name} is not set. Copy .env.example to .env and fill it in.")
    return val


def provider() -> str:
    p = os.environ.get("EMBEDDING_PROVIDER", "local").strip().lower()
    if p not in ("openrouter", "local"):
        raise RuntimeError(f"EMBEDDING_PROVIDER must be 'openrouter' or 'local', got {p!r}")
    return p


def dimensions() -> int:
    return int(os.environ.get("EMBEDDING_DIMENSIONS", "768"))


def model_id() -> str:
    """Identifier to store with each vector, e.g. 'openrouter:google/gemini-embedding-2@768'."""
    if provider() == "local":
        return f"local:google/embeddinggemma-2@{dimensions()}"
    return f"openrouter:{os.environ.get('EMBEDDING_MODEL', 'google/gemini-embedding-2')}@{dimensions()}"


def _post(url: str, key: str, body: bytes, content_type: str, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": content_type},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{url} -> HTTP {e.code}: {e.read()[:300].decode(errors='replace')}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach {url}: {e.reason}") from None
    if "error" in data:
        raise RuntimeError(f"{url} -> {data['error']}")
    return data


def _normalise(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _vectors(data: dict) -> list[list[float]]:
    rows = sorted(data["data"], key=lambda d: d.get("index", 0))
    return [_normalise(d["embedding"]) for d in rows]


def embed(texts: Union[str, Sequence[str]], kind: Kind = "document") -> list[list[float]]:
    """Embed text. Use kind="query" for search text, "document" for content being indexed."""
    items = [texts] if isinstance(texts, str) else list(texts)
    out: list[list[float]] = []
    for i in range(0, len(items), BATCH):
        chunk = items[i : i + BATCH]
        if provider() == "local":
            url = _cfg("LOCAL_EMBEDDING_URL").rstrip("/") + "/v1/embeddings"
            body = {"input": chunk, "input_type": kind, "dimensions": dimensions()}
            data = _post(url, _cfg("LOCAL_EMBEDDING_KEY"), json.dumps(body).encode(), "application/json")
        else:
            body = {
                "model": os.environ.get("EMBEDDING_MODEL", "google/gemini-embedding-2"),
                "input": chunk,  # kind only affects the local model
                "dimensions": dimensions(),
            }
            data = _post(OPENROUTER_URL, _cfg("OPENROUTER_API_KEY"), json.dumps(body).encode(), "application/json")
        out.extend(_vectors(data))
    return out


def embed_file(path: Union[str, Path]) -> list[float]:
    """Embed an image (both providers) or a video/audio file (local provider only)."""
    path = Path(path)
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    raw = path.read_bytes()
    if provider() == "local":
        boundary = uuid.uuid4().hex
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{path.name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n".encode() + raw
            + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"dimensions\"\r\n\r\n{dimensions()}"
              f"\r\n--{boundary}--\r\n".encode()
        )
        url = _cfg("LOCAL_EMBEDDING_URL").rstrip("/") + "/v1/embeddings/file"
        return _vectors(_post(url, _cfg("LOCAL_EMBEDDING_KEY"), body, f"multipart/form-data; boundary={boundary}", 300))[0]
    if not mime.startswith("image/"):
        raise ValueError(f"OpenRouter path supports images only here; got {mime}. Use EMBEDDING_PROVIDER=local "
                         "for video/audio, or embed extracted keyframes/transcripts.")
    data_url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    body = {
        "model": os.environ.get("EMBEDDING_MODEL", "google/gemini-embedding-2"),
        "input": [{"content": [{"type": "image_url", "image_url": {"url": data_url}}]}],
        "dimensions": dimensions(),
    }
    return _vectors(_post(OPENROUTER_URL, _cfg("OPENROUTER_API_KEY"), json.dumps(body).encode(), "application/json"))[0]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


if __name__ == "__main__":
    # Smoke test: python api/embeddings.py
    docs = ["Wind forecast: gusts to 30 mph Thursday, flights grounded.",
            "Curtain wall RFI #12: confirm mullion spacing on level 14.",
            "Lunch order for the site team on Friday."]
    q = embed("can we fly in high wind?", kind="query")[0]
    print(f"provider={model_id()}")
    for score, d in sorted(((cosine(q, v), d) for v, d in zip(embed(docs), docs)), reverse=True):
        print(f"  {score:.3f}  {d}")
