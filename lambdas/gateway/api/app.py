import logging

from api.quota import write_quota_updates_to_dynamo
import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from mangum import Mangum
from contextlib import asynccontextmanager
from anyio import to_thread
from apscheduler.schedulers.background import BackgroundScheduler

from api.routers import model, chat, embeddings
from api.setting import API_ROUTE_PREFIX, TITLE, DESCRIPTION, SUMMARY, VERSION

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    to_thread.current_default_thread_limiter().total_tokens = 1000
    scheduler.add_job(write_quota_updates_to_dynamo, 'interval', minutes=10)
    scheduler.start()
    yield

config = {
    "title": TITLE,
    "description": DESCRIPTION,
    "summary": SUMMARY,
    "version": VERSION,
    "lifespan": lifespan
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
app = FastAPI(**config)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(model.router, prefix=API_ROUTE_PREFIX)
app.include_router(chat.router, prefix=API_ROUTE_PREFIX)
app.include_router(embeddings.router, prefix=API_ROUTE_PREFIX)


@app.get("/health")
async def health():
    """For health check if needed"""
    return {"status": "OK"}


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return PlainTextResponse(str(exc), status_code=400)


handler = Mangum(app)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
