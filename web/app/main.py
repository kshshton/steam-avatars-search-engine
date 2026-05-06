from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints import router as v1_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)
app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
IMAGE_DIR_CANDIDATES = [
    PROJECT_ROOT / "Images",
    PROJECT_ROOT / "images",
]

IMAGE_DIR = next((path for path in IMAGE_DIR_CANDIDATES if path.exists()), None)
if IMAGE_DIR is None:
    raise RuntimeError("Could not find an Images/images directory at project root.")

app.mount("/images", StaticFiles(directory=str(IMAGE_DIR)), name="images")

@app.get("/")
def index() -> HTMLResponse:
    image_suffixes = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
    image_files = sorted(
        [
            file.name
            for file in IMAGE_DIR.iterdir()
            if file.is_file() and file.suffix.lower() in image_suffixes
        ]
    )
    cards = "\n".join(
        f'<div class="card"><img src="/images/{name}" alt="{name}" loading="lazy" />'
        f'<p></p></div>'
        for name in image_files
    )
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
      margin: 0 0 0;
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
    }}
    @media (max-width: 500px) {{
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <h1>Image Gallery ({len(image_files)})</h1>
  <div class="grid">{cards}</div>
</body>
</html>"""
    return HTMLResponse(content=html)
