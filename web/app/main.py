from fastapi import FastAPI

from app.api.v1.endpoints import router as v1_router
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)
app.include_router(v1_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
