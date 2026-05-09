# Steam Avatars Search Engine

Semantic search for Steam avatar GIFs using CLIP embeddings, ChromaDB, and a FastAPI UI.

## Repository Structure

- `avatars.csv` - source avatar URLs and scrape timestamps.
- `images/` - local avatar files used by the web app and indexer.
- `steam_avatars_db/` - persistent ChromaDB data.
- `notebooks/embeddings.ipynb` - download, embed, and index pipeline.
- `notebooks/accuracy_testing.ipynb` - retrieval results tests.
- `web/` - FastAPI app.

## Search Pipeline

1. URLs are read from `avatars.csv`.
2. Avatars are stored locally (ID-based filenames) in `images/`.
3. CLIP image embeddings are inserted into Chroma collection `steam_avatars_collection`.
4. Query text is embedded with CLIP text encoder.
5. Chroma nearest-neighbor search returns top results.
6. UI renders local image path first, then falls back to metadata `url` if loading fails.

## Setup

Use separate virtual environments for data/indexing and web serving.

### Notebook / indexing environment

```bash
python -m venv venv-notebooks
source venv-notebooks/bin/activate
pip install -r requirements.txt
```

### Web app environment

```bash
python -m venv web/venv-web
source web/venv-web/bin/activate
pip install -r web/requirements.txt
```

## Build or Refresh Index

1. Activate `venv-notebooks`.
2. Run `notebooks/embeddings.ipynb` top-to-bottom.
3. Verify:
   - local images exist under `images/`,
   - vectors are written to `steam_avatars_db/`.

Optional: run `notebooks/accuracy_testing.ipynb` to evaluate retrieval quality.

## Run Web App

```bash
source web/venv-web/bin/activate
cd web
uvicorn app.main:app --reload --port 8001
```

Open:

- `http://127.0.0.1:8001/` - gallery
- `http://127.0.0.1:8001/?q=skeleton&n=20` - query example

## Configuration

Set in `web/.env`:

- `PROJECT_NAME` - page/app title

### HNSW Tuning (in `web/app/main.py`)

- `space = cosine`
- `ef_construction = 600`
- `max_neighbors = 48`
- `ef_search = 128`
- `num_threads = min(8, cpu_count)`
- `resize_factor = 1.2`
- `batch_size = 512`
- `sync_threshold = 2000`

These settings target fast query latency with strong recall.
If your collection already exists, rebuild it to guarantee new index settings are applied.

## Troubleshooting

- **Server error on search**
  - Ensure `web/venv-web` dependencies are installed.
  - Confirm local CLIP model files are available in cache.

- **Images missing in UI**
  - Confirm `images/` or `Images/` exists at repo root.
  - Re-run `notebooks/embeddings.ipynb` so local files and index are in sync.
  - Validate metadata URLs if fallback is needed.

- **Model download/network issues**
  - Run notebooks once with internet access to populate Hugging Face cache.

