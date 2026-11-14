"""EmbeddingGemma 2 embedding server for the team.

Endpoints (all but /health need `Authorization: Bearer <key>`):
  GET  /health                 -> liveness, no auth
  POST /v1/embeddings          -> OpenAI-compatible text embeddings
  POST /v1/embeddings/media    -> multimodal: JSON list of text / base64 image items
  POST /v1/embeddings/file     -> upload one image, video or audio file (multipart)
"""

import asyncio
import base64
import io
import os
import secrets
import tempfile
import time
from pathlib import Path
from typing import Literal, Optional, Union

import torch
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from PIL import Image
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer

MODEL_ID = os.environ.get("MODEL_ID", "google/embeddinggemma-2")
MAX_ITEMS = int(os.environ.get("MAX_ITEMS", "256"))
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "200"))


def _load_keys() -> set[str]:
    env_file = Path(__file__).with_name(".env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    keys = {k.strip() for k in os.environ.get("API_KEYS", "").split(",") if k.strip()}
    if not keys:
        raise SystemExit("No API_KEYS set. Run: python make_key.py")
    return keys


API_KEYS = _load_keys()
device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
print(f"Loading {MODEL_ID} on {device}...")
model = SentenceTransformer(MODEL_ID, device=device)
DIM = model.get_embedding_dimension()
print(f"Ready: {DIM}-dim embeddings")

# The GPU model is not safe to call from several threads at once: serialize calls.
_lock = asyncio.Lock()
app = FastAPI(title="EmbeddingGemma 2 server")
bearer = HTTPBearer(auto_error=False)


def require_key(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> None:
    if creds is None or not any(secrets.compare_digest(creds.credentials, k) for k in API_KEYS):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


async def _encode(items, prompt_name: Optional[str], dimensions: Optional[int]):
    def run():
        kwargs = {"normalize_embeddings": True, "batch_size": 16}
        if prompt_name:
            kwargs["prompt_name"] = prompt_name
        if dimensions:
            kwargs["truncate_dim"] = dimensions
        return model.encode(items, **kwargs)

    async with _lock:
        t = time.time()
        vecs = await asyncio.to_thread(run)
        return vecs, time.time() - t


def _check_dims(dimensions: Optional[int]) -> None:
    if dimensions is not None and not (32 <= dimensions <= DIM):
        raise HTTPException(400, f"dimensions must be between 32 and {DIM}")


def _response(vecs, elapsed: float, n_tokens: int = 0):
    return {
        "object": "list",
        "model": MODEL_ID,
        "data": [{"object": "embedding", "index": i, "embedding": v.tolist()} for i, v in enumerate(vecs)],
        "usage": {"prompt_tokens": n_tokens, "total_tokens": n_tokens},
        "elapsed_ms": round(elapsed * 1000),
    }


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_ID, "device": device, "dimensions": DIM}


# ---------- OpenAI-compatible text endpoint ----------

class TextRequest(BaseModel):
    input: Union[str, list[str]]
    model: Optional[str] = None  # accepted for OpenAI client compatibility, ignored
    input_type: Literal["query", "document"] = Field(
        "document", description="'query' for search queries, 'document' for content being indexed"
    )
    dimensions: Optional[int] = None


@app.post("/v1/embeddings", dependencies=[Depends(require_key)])
async def embed_text(req: TextRequest):
    texts = [req.input] if isinstance(req.input, str) else req.input
    if not texts or len(texts) > MAX_ITEMS:
        raise HTTPException(400, f"input must have 1-{MAX_ITEMS} items")
    _check_dims(req.dimensions)
    vecs, elapsed = await _encode(texts, req.input_type, req.dimensions)
    n_tokens = sum(len(model.tokenizer(t)["input_ids"]) for t in texts)
    return _response(vecs, elapsed, n_tokens)


# ---------- Multimodal JSON endpoint (text + base64 images) ----------

class MediaItem(BaseModel):
    text: Optional[str] = None
    image_base64: Optional[str] = None


class MediaRequest(BaseModel):
    items: list[MediaItem]
    dimensions: Optional[int] = None


@app.post("/v1/embeddings/media", dependencies=[Depends(require_key)])
async def embed_media(req: MediaRequest):
    """Text and images share one vector space, so results compare directly with /v1/embeddings
    (embed search queries there with input_type='query')."""
    if not req.items or len(req.items) > MAX_ITEMS:
        raise HTTPException(400, f"items must have 1-{MAX_ITEMS} entries")
    _check_dims(req.dimensions)
    inputs = []
    for i, it in enumerate(req.items):
        if it.image_base64:
            try:
                raw = it.image_base64.split(",", 1)[-1]  # allow data: URLs
                img = Image.open(io.BytesIO(base64.b64decode(raw))).convert("RGB")
            except Exception:
                raise HTTPException(400, f"items[{i}].image_base64 is not a readable image")
            inputs.append({"image": img, "text": it.text} if it.text else {"image": img})
        elif it.text:
            inputs.append(it.text)
        else:
            raise HTTPException(400, f"items[{i}] needs text or image_base64")
    vecs, elapsed = await _encode(inputs, None, req.dimensions)
    return _response(vecs, elapsed)


# ---------- File upload endpoint (drag-and-drop from the canvas) ----------

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}


@app.post("/v1/embeddings/file", dependencies=[Depends(require_key)])
async def embed_file(file: UploadFile = File(...), dimensions: Optional[int] = Form(None)):
    _check_dims(dimensions)
    ext = Path(file.filename or "").suffix.lower()
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"file larger than {MAX_UPLOAD_MB} MB")
    if ext in IMAGE_EXT:
        try:
            item = {"image": Image.open(io.BytesIO(data)).convert("RGB")}
        except Exception:
            raise HTTPException(400, "not a readable image")
        vecs, elapsed = await _encode([item], None, dimensions)
    elif ext in VIDEO_EXT or ext in AUDIO_EXT:
        kind = "video" if ext in VIDEO_EXT else "audio"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(data)
            path = tmp.name
        try:
            vecs, elapsed = await _encode([{kind: path}], None, dimensions)
        except Exception as e:
            raise HTTPException(400, f"could not embed {kind}: {e}")
        finally:
            os.unlink(path)
    else:
        raise HTTPException(415, f"unsupported file type '{ext}'. Send text through /v1/embeddings.")
    out = _response(vecs, elapsed)
    out["filename"] = file.filename
    return out
