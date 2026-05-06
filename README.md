# Steam Avatars Search Engine

Local semantic search for Steam avatar GIFs using CLIP embeddings + ChromaDB, with a FastAPI web UI.

## Repository Structure

- `avatars.csv` - source URLs for avatar images.
- `images/` - locally cached GIF files (saved as IDs, e.g. `uuid.gif`).
- `steam_avatars_db/` - ChromaDB persistent index.
- `notebooks/embeddings.ipynb` - data prep, image download, embedding generation, and indexing.
- `notebooks/accuracy_testing.ipynb` - search quality checks against the indexed collection.
- `web/` - FastAPI app and web UI.
- `requirements.txt` - notebook/data pipeline dependencies.

## How It Works

1. Read avatar URLs from `avatars.csv`.
2. Generate a UUID per image and save images to `images/<id>.gif`.
3. Embed images with CLIP and store vectors in ChromaDB (`steam_avatars_collection`).
4. In the web app, convert user text query into a CLIP text embedding.
5. Query ChromaDB for nearest results and display matching GIFs in a grid.

## Setup

Use separate Python environments for notebooks and web app.

### 1) Notebook / indexing environment

From repository root:

```bash
python -m venv venv-notebooks
source venv-notebooks/bin/activate
pip install -r requirements.txt
```

### 2) Web app environment

From repository root:

```bash
python -m venv web/venv-web
source web/venv-web/bin/activate
pip install -r web/requirements.txt
```

## Build or Refresh the Index

1. Activate `venv-notebooks`.
2. Open and run `notebooks/embeddings.ipynb` top-to-bottom.
3. This will:
   - cache images into `images/`,
   - write/update vectors in `steam_avatars_db/`.

Optional: use `notebooks/accuracy_testing.ipynb` to validate search quality.

## Run the Web App

From repository root:

```bash
source web/venv-web/bin/activate
cd web
uvicorn app.main:app --reload --port 8001
```

Open:

- `http://127.0.0.1:8001/` - gallery page
- `http://127.0.0.1:8001/?q=skeleton&n=20` - search query
- `http://127.0.0.1:8001/docs` - FastAPI docs

## Screenshot

![Steam Avatars Search Engine Screenshot](docs/demo.png)

## Configuration

Edit `web/.env`:

- `PROJECT_NAME` - page/app name
- `API_V1_PREFIX` - API route prefix

## Troubleshooting

- **Internal Server Error on search**  
  Ensure web dependencies are installed in `web/venv-web`.

- **No search results rendered**  
  Rebuild index with `notebooks/embeddings.ipynb` and confirm `images/` + `steam_avatars_db/` are in sync.

- **Model download/network issues**  
  Run notebooks once in an environment with internet so model artifacts are cached locally.

