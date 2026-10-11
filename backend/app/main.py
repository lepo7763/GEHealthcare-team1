from fastapi import FastAPI
from app.health.router import router as health_router
from app.log_collection.router import router as logs_router

app = FastAPI(title="IoMT Analysis Tool", version="0.1.0")


app.include_router(health_router)
app.include_router(logs_router)