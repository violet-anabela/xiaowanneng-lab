"""共享 schema 与常量。"""

from pydantic import BaseModel

SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}


class HealthStatus(BaseModel):
    status: str
