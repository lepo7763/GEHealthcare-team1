"""Params for collecting Axone logs as part of a diagnostic package."""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AxoneLogParams(BaseModel):
    """Axone export filters, sent as query params on /api/logs/zip.

    Everything is optional at the HTTP layer because the params are only
    meaningful when the ``axone-logs`` service is selected; the router validates
    them (via ``validate_export``) before the collection starts. 
    """

    axone_scope: Literal["device", "all"] = Field(
        default="device",
        description="Export one device's logs or all devices' logs",
    )
    axone_start_timestamp: Optional[str] = Field(
        default=None,
        description="Local start time, YYYY-MM-DDTHH:mm:ss.SSS (no time zone)",
    )
    axone_end_timestamp: Optional[str] = Field(
        default=None,
        description="Local end time, YYYY-MM-DDTHH:mm:ss.SSS (no time zone)",
    )
    axone_device_uuid: Optional[str] = Field(
        default=None,
        description="Device/source UUID; required when axone_scope=device",
    )
    axone_event_category: Optional[int] = Field(
        default=None,
        description="Optional numeric event category filter",
    )
