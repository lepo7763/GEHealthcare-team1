"""Manual smoke script for the UMF RTI capture service.

Run from backend/ with a valid ~/.kube/config:

    .venv/bin/python test.py

This is not a pytest test (the pytest suite is in tests/).
"""

from app.core.k8s_client import get_batch_v1_api, get_core_v1_api
from app.umf_rti.config import get_umf_rti_config
from app.umf_rti.schemas import UmfRtiParams
from app.umf_rti.service import capture_umf_rti

result = capture_umf_rti(
    get_core_v1_api(),
    get_batch_v1_api(),
    UmfRtiParams(umf_domain_id=32, umf_duration_seconds=30),
    get_umf_rti_config(),
)
print("Result summary:", result.model_dump(exclude={"log_text"}))
