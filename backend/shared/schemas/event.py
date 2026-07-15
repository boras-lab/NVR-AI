from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any
from shared.models.event import EventCategory, EventSeverity

class EventBase(BaseModel):
    category: EventCategory
    severity: EventSeverity = EventSeverity.INFO
    description: str
    camera_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    metadata_json: Optional[Dict[str, Any]] = None

class EventCreate(EventBase):
    pass

class EventResponse(EventBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
