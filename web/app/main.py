import os
import json
from functools import lru_cache
from html import escape
from pathlib import Path
from urllib.parse import quote

import chromadb
import numpy as np
import torch
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from transformers import AutoTokenizer, CLIPModel

from app.core.config import settings

# Force offline mode to avoid background Hub calls in restricted environments.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

app = FastAPI(title=settings.PROJECT_NAME)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
IMAGE_DIR_CANDIDATES = [
    PROJECT_ROOT / "Images",
    PROJECT_ROOT / "images",
]
CHROMA_DB_PATH = PROJECT_ROOT / "steam_avatars_db"
CHROMA_COLLECTION = "steam_avatars_collection"
HF_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"

IMAGE_DIR = next((path for path in IMAGE_DIR_CANDIDATES if path.exists()), None)
if IMAGE_DIR is None:
    raise RuntimeError("Could not find an Images/images directory at project root.")

app.mount("/images", StaticFiles(directory=str(IMAGE_DIR)), name="images")


@lru_cache(maxsize=1)
def _load_models() -> tuple[CLIPModel, AutoTokenizer]:
    model_name = "openai/clip-vit-base-patch32"
    try:
        model = CLIPModel.from_pretrained(
            model_name,
            local_files_only=True,
            cache_dir=str(HF_CACHE_DIR),
            use_safetensors=False,
        )
        tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            local_files_only=True,
            cache_dir=str(HF_CACHE_DIR),
        )
    except Exception as exc:  # pragma: no cover - depends on local cache presence
        raise RuntimeError(
            "CLIP model is not available locally. "
            "Download it once in this environment or run with internet access."
        ) from exc
    return model, tokenizer


@lru_cache(maxsize=1)
def _get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))
    return client.get_or_create_collection(name=CHROMA_COLLECTION)


def search(text: str, n_results: int = 20) -> list[dict[str, float | str]]:
    model, tokenizer = _load_models()
    collection = _get_collection()

    inputs = tokenizer([text], return_tensors="pt", padding=True, truncation=True)
    with torch.no_grad():
        outputs = model.get_text_features(**inputs)

    if hasattr(outputs, "pooler_output"):
        embedding = outputs.pooler_output
    elif isinstance(outputs, torch.Tensor):
        embedding = outputs
    else:
        embedding = outputs[0]
    embedding = embedding[0] if embedding.ndim > 1 else embedding
    embedding = embedding / embedding.norm(p=2)
    embedding = embedding.cpu().numpy().astype(np.float32)

    results = collection.query(query_embeddings=[embedding.tolist()], n_results=n_results)
    ids = results.get("ids", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    return [
        {
            "id": image_id,
            "url": (metadata or {}).get("url", ""),
            "distance": float(distance),
        }
        for image_id, metadata, distance in zip(ids, metadatas, distances)
        if image_id
    ]


@app.get("/")
def index(q: str | None = Query(default=None), n: int = Query(default=20, ge=1, le=100)) -> HTMLResponse:
    image_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
    query = (q or "").strip()

    error_message = ""
    if query:
        try:
            results = search(query, n_results=n)
        except Exception as exc:
            results = []
            error_message = str(exc)
        cards = "\n".join(
            "<div class=\"card\">"
            f"<img class=\"result-image\" src=\"{escape(_build_image_sources(result)[0])}\" "
            f"data-fallbacks=\"{escape(json.dumps(_build_image_sources(result)), quote=True)}\" "
            f"alt=\"{escape(_id_to_filename(str(result['id'])))}\" loading=\"lazy\" />"
            f"<p>distance: {result['distance']:.4f}</p>"
            "</div>"
            for result in results
        )
        title = f"Search results for '{escape(query)}' ({len(results)})"
    else:
        image_files = sorted(
            [
                file.name
                for file in IMAGE_DIR.iterdir()
                if file.is_file() and file.suffix.lower() in image_suffixes
            ]
        )
        cards = "\n".join(
            "<div class=\"card\">"
            f"<img src=\"/images/{quote(name)}\" alt=\"{escape(name)}\" loading=\"lazy\" />"
            "</div>"
            for name in image_files
        )
        title = f"Image gallery ({len(image_files)})"

    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{settings.PROJECT_NAME}</title>
  <style>
    body {{
      margin: 0;
      padding: 16px;
      font-family: Arial, sans-serif;
      background: #121212;
      color: #f5f5f5;
    }}
    h1 {{
      margin: 0 0 16px;
      font-size: 20px;
    }}
    .search-form {{
      display: flex;
      gap: 8px;
      margin-bottom: 16px;
    }}
    .search-form input, .search-form button, .search-form a {{
      border-radius: 8px;
      border: 1px solid #2b2b2b;
      background: #1b1b1b;
      color: #f5f5f5;
      padding: 8px 10px;
      text-decoration: none;
      font-size: 14px;
    }}
    .search-form input[type="text"] {{
      flex: 1;
      min-width: 220px;
    }}
    .search-form input[type="number"] {{
      width: 80px;
    }}
    .error {{
      color: #ff7a7a;
      min-height: 18px;
      margin: 0 0 12px;
      font-size: 13px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 12px;
    }}
    .card {{
      background: #1b1b1b;
      border: 1px solid #2b2b2b;
      border-radius: 8px;
      padding: 8px;
      overflow: hidden;
    }}
    .card img {{
      width: 100%;
      aspect-ratio: 1 / 1;
      object-fit: cover;
      display: block;
      border-radius: 6px;
    }}
    .card p {{
      margin: 8px 0 0;
      font-size: 12px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    @media (max-width: 1400px) {{
      .grid {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    }}
    @media (max-width: 1100px) {{
      .grid {{ grid-template-columns: repeat(3, minmax(0, 1fr)); }}
    }}
    @media (max-width: 800px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .search-form {{ flex-wrap: wrap; }}
    }}
    @media (max-width: 500px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <form method="get" class="search-form">
    <input type="text" name="q" value="{escape(query)}" placeholder="Search avatars (e.g. anime girl, skeleton)" />
    <input type="number" name="n" value="{n}" min="1" max="100" />
    <button type="submit">Search</button>
    <a href="/">Reset</a>
  </form>
  <p class="error">{escape(error_message)}</p>
  <div class="grid">{cards}</div>
  <script>
    for (const img of document.querySelectorAll(".result-image")) {{
      const fallbacksRaw = img.dataset.fallbacks || "[]";
      let fallbacks = [];
      try {{
        fallbacks = JSON.parse(fallbacksRaw);
      }} catch (_err) {{
        fallbacks = [img.currentSrc || img.src];
      }}

      // Remove duplicates but keep order.
      fallbacks = [...new Set(fallbacks.filter(Boolean))];
      let index = 0;
      let retriedCurrent = false;

      img.addEventListener("error", () => {{
        if (!retriedCurrent) {{
          retriedCurrent = true;
          const separator = img.src.includes("?") ? "&" : "?";
          img.src = img.src + separator + "_retry=" + Date.now();
          return;
        }}
        retriedCurrent = false;
        index += 1;
        if (index < fallbacks.length) {{
          img.src = fallbacks[index];
        }}
      }});
    }}
  </script>
</body>
</html>"""
    return HTMLResponse(content=html)


def _id_to_filename(image_id: str) -> str:
    return image_id if "." in image_id else f"{image_id}.gif"


def _resolve_image_src(result: dict[str, float | str]) -> str:
    return _build_image_sources(result)[0]


def _build_image_sources(result: dict[str, float | str]) -> list[str]:
    filename = _id_to_filename(str(result["id"]))
    sources: list[str] = []
    local_path = IMAGE_DIR / filename
    if local_path.exists():
        sources.append(f"/images/{quote(filename)}")

    url = str(result.get("url", ""))
    if url:
        sources.append(url)

    if not sources:
        sources.append(f"/images/{quote(filename)}")
    return sources


def _resolve_display_name(result: dict[str, float | str]) -> str:
    filename = _id_to_filename(str(result["id"]))
    if (IMAGE_DIR / filename).exists():
        return filename
    url = str(result.get("url", ""))
    return url.rsplit("/", maxsplit=1)[-1] if url else filename
