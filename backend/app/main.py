from fastapi import FastAPI
from app.health.router import router as health_router

app = FastAPI(title="IoMT Analysis Tool", version="0.1.0")


app.include_router(health_router)