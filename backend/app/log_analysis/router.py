from fastapi import APIRouter, File, HTTPException, UploadFile

from .privacy import scan_log_archive
from .schemas import AnalysisReport, PrivacyReport
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


@router.post("/privacy", response_model=PrivacyReport)
def scan_log_zip_for_privacy(
    file: UploadFile = File(..., description="Zip from GET /api/logs/zip"),
):
    # Same upload and error handling as /zip; only the scan differs
    try:
        return scan_log_archive(file.file)
    except InvalidLogArchiveError as e:
        raise HTTPException(status_code=400, detail=str(e))
