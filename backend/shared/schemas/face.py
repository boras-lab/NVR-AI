from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional
from shared.models.face import FaceTag

class FaceBase(BaseModel):
    person_name: Optional[str] = None
    is_known: bool = False
    similarity_score: Optional[float] = None
    camera_id: Optional[UUID] = None
    photo_url: Optional[str] = None
    tag: FaceTag = FaceTag.UNKNOWN

class FaceCreate(FaceBase):
    pass

class FaceUpdate(BaseModel):
    person_name: Optional[str] = None
    is_known: Optional[bool] = None
    tag: Optional[FaceTag] = None
    visit_count: Optional[int] = None
    last_seen: Optional[datetime] = None

class FaceResponse(FaceBase):
    id: UUID
    first_seen: datetime
    last_seen: datetime
    visit_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
