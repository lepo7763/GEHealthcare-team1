from typing import List

from app.umf_rti.config import UmfRtiConfig, get_umf_rti_config
from fastapi import APIRouter, Depends
from pydantic import BaseModel

router = APIRouter(prefix="/api/umf-rti", tags=["UMF RTI"])


class UmfRtiDomainOption(BaseModel):
    domain: int
    label: str


@router.get("/domains", response_model=List[UmfRtiDomainOption])
def list_domains(config: UmfRtiConfig = Depends(get_umf_rti_config)):
    """Friendly domain labels for the capture dropdown (the value is the number).

    Served from config (deployment-specific) rather than hardcoded in the
    frontend. The combined diagnostics capture itself goes through
    ``/api/logs/zip?services=umf-rti``.
    """
    return [
        UmfRtiDomainOption(domain=domain, label=label)
        for domain, label in config.domain_labels.items()
    ]
