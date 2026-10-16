from fastapi import APIRouter, File, HTTPException, UploadFile

from .schemas import AnalysisReport
from .service import analyze_log_archive, InvalidLogArchiveError

router = APIRouter(prefix="/api/analysis", tags=["Log Analysis"])


@router.post("/zip", response_model=AnalysisReport)
def analyze_log_zip(file: UploadFile = File(..., description="Zip from GET /api/logs/zip")):
    # Sync `def` (not `async def`) so FastAPI runs this in a worker thread;
    # unzipping and regex over big logs would otherwise block every other request.
    try:
        return analyze_log_archive(file.file)
    except InvalidLogArchiveError as e:
        # 400 rather than 500: the server is fine, the uploaded file is the problem
        raise HTTPException(status_code=400, detail=str(e))
