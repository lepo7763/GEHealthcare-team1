from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.health.router import router as health_router
from app.log_collection.router import router as logs_router
from app.environments.router import router as environments_router
from app.log_analysis.router import router as analysis_router

app = FastAPI(title="IoMT Analysis Tool", version="0.1.0")


app.include_router(health_router)
app.include_router(logs_router)
app.include_router(environments_router)
app.include_router(analysis_router)

# Prototype page for the "Analyze Package" step at /analysis/. Served by the backend itself
# so it works offline in the lab and needs no CORS setup; will move into the React frontend.
app.mount(
    "/analysis",
    StaticFiles(directory=Path(__file__).parent / "log_analysis" / "static", html=True),
    name="analysis-ui",
)
