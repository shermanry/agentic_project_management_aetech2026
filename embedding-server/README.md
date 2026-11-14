# Embedding server (EmbeddingGemma 2)

Serves Google's open `google/embeddinggemma-2` model over HTTP with API keys. Text, images, video and audio all land in **one 768-dim vector space**, so any of them compare directly. `api/embeddings.py` and the northstar app call it when `EMBEDDING_PROVIDER=local`.

Ryan's Mac normally hosts it at `http://10.70.4.24:8000` (the Wi-Fi address; it changes if the Mac reconnects). Follow this guide to run your own copy on another computer.

## Set it up on a new computer

You need about 4 GB of free disk space (model plus libraries) and 8 GB of RAM or more. A GPU is optional: Apple Silicon (M1 to M4) and NVIDIA are used automatically; otherwise it runs on the CPU, more slowly.

**1. Install the tools.**

| | Mac | Linux | Windows |
| --- | --- | --- | --- |
| uv (Python manager) | `brew install uv` | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| ffmpeg (video and audio only) | `brew install ffmpeg` | `sudo apt install ffmpeg` | `winget install ffmpeg` |

**2. Create the environment** (from the repo root):

```bash
cd embedding-server
uv venv --python 3.12
```

NVIDIA GPU only: install the CUDA build of PyTorch first, using the command from [pytorch.org](https://pytorch.org/get-started/locally/) with `uv pip install` in place of `pip install`.

```bash
uv pip install -r requirements.txt
```

**3. Create an API key.** This writes `embedding-server/.env`, which git ignores:

```bash
.venv/bin/python make_key.py
```

Windows: `.venv\Scripts\python make_key.py`. Run it again to add one key per teammate; restart the server after adding keys.

**4. Start the server.**

```bash
./start.sh
```

Windows: `.venv\Scripts\uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1`

The first start downloads the model from Hugging Face (about 1.5 GB, a few minutes). Later starts load it in about 20 seconds. It is ready when it prints `Ready: 768-dim embeddings`. Leave that window open.

**5. Check it.**

```bash
curl http://localhost:8000/health
```

You should get `{"status":"ok",...}` with `"device":"mps"` (Mac), `"cuda"` (NVIDIA) or `"cpu"`.

**6. Let teammates in.**

- Find your address: Mac `ipconfig getifaddr en0`, Windows `ipconfig` (IPv4 Address), Linux `hostname -I`.
- Allow incoming connections through the firewall. On a Mac: System Settings, Network, Firewall, Options, then allow the Python inside `.venv` (or click Allow when macOS asks). On Windows: allow Python when the firewall prompt appears.
- Ask a teammate on the same Wi-Fi to run `curl http://<your address>:8000/health`. If it hangs, the Wi-Fi blocks laptop-to-laptop traffic; use a tunnel or the OpenRouter fallback (`EMBEDDING_PROVIDER=openrouter`).
- Teammates set `LOCAL_EMBEDDING_URL` and `LOCAL_EMBEDDING_KEY` in the repo-root `.env`.
- Keep the computer awake while serving. Mac: `caffeinate -dis ./start.sh`.

Vectors from different models are not comparable. If the team switches between this server and OpenRouter's Gemini Embedding 2, everything stored must be re-embedded.

## Endpoints

Every call except `/health` needs `Authorization: Bearer <key>`.

| Method | Path | Body | Use for |
| --- | --- | --- | --- |
| GET | `/health` | none | Is it up? |
| POST | `/v1/embeddings` | `{"input": str or [str], "input_type": "document" or "query", "dimensions"?: int}` | Text. OpenAI-compatible |
| POST | `/v1/embeddings/media` | `{"items": [{"text"?: str, "image_base64"?: str}], "dimensions"?: int}` | Images, or image + caption, as JSON |
| POST | `/v1/embeddings/file` | multipart `file=@photo.jpg` (+ optional `dimensions`) | Uploads: images, video (`.mp4 .mov ...`), audio |

- `input_type`: `"document"` when indexing content, `"query"` for search text. It matters for ranking.
- `dimensions`: optional, 32 to 768. Use the same value everywhere (the repo uses 768).
- Up to 256 items per call; uploads up to 200 MB. PDFs: extract text first and send it to `/v1/embeddings`.
- Vectors are normalised, so cosine similarity is a dot product.

```bash
curl -s $BASE/v1/embeddings -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"input": ["Wind gusts to 30 mph Thursday"], "input_type": "document"}'
```

```bash
curl -s $BASE/v1/embeddings/file -H "Authorization: Bearer $KEY" -F file=@site_photo.jpg
```

## Speed (measured on an M4 MacBook Air)

| Input | Speed |
| --- | --- |
| Single search query | about 25 ms |
| Text chunks of ~250 tokens, batched | about 17 per second |
| One 1024x768 image | about 0.9 s |
| 5-second video clip | about 2.2 s |

One request runs at a time and others queue, so batch text (about 32 chunks per call). Half precision was no faster on the M4. A machine without a GPU will be several times slower.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `No API_KEYS set` on start | Run `make_key.py` (step 3) |
| 401 from every call | Wrong or missing key, or a key added since the server started: restart it |
| Video upload says `torchcodec` is missing or can't load | Install ffmpeg (step 1), then `uv pip install torchcodec`. Text and images work without it |
| `address already in use` | Something else is on port 8000: stop it, or `PORT=8001 ./start.sh` |
| Teammates time out | Firewall or Wi-Fi isolation (step 6) |
| Python 3.9 errors | The system Python is too old; always use the `.venv` that `uv venv --python 3.12` made |

## Files

| File | What it does |
| --- | --- |
| `server.py` | FastAPI app: loads the model, checks keys, serves the endpoints |
| `make_key.py` | Adds a random API key to `.env` |
| `start.sh` | Starts the server on `0.0.0.0` (Mac and Linux) |
| `requirements.txt` | Python packages |
