from pydantic import BaseModel, Field
from fastapi import Query


class UmfRtiParams(BaseModel):
    # less than 232 cuz anything higher produces a port number higher than 65535.
    # Assuming worst case in formula: Port = 7400 + (250 * domain_id) + offset + (2 * participant_id)
    umf_domain_id: int = Field(
        default=Query(default=32, ge=0, le=232, description="DDS Domain ID to inspect")
    )
    umf_duration_seconds: int = Field(
        default=Query(
            default=120,  # router's delay and timeout are both 60, so 120 should give second shot
            ge=30,  # handshake w/ router can fail. Lower can give false negatives
            le=600,  # we don't have the mem to go higher
            description="Duration in seconds for the UMF RTI capture",
        )
    )
