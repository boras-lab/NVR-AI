from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any
from shared.models.alert import AlertStatus

class AlertBase(BaseModel):
    camera_id: UUID
    event_type: str
    object_type: str
    confidence: float
    snapshot_url: Optional[str] = None
    clip_url: Optional[str] = None
    status: AlertStatus = AlertStatus.NEW
    metadata_json: Optional[Dict[str, Any]] = None
    telegram_sent: bool = False

class AlertCreate(AlertBase):
    pass

class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    telegram_sent: Optional[bool] = None

class AlertResponse(AlertBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
