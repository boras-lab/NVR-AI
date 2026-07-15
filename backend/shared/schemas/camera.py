from pydantic import BaseModel, HttpUrl, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Dict, Any
from shared.models.camera import CameraStatus

class CameraBase(BaseModel):
    name: str = Field(..., max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    rtsp_url: str = Field(..., max_length=500)
    username: Optional[str] = Field(None, max_length=100)
    detection_lines: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    # Password is not included in base to prevent accidental exposure

class CameraCreate(CameraBase):
    password: Optional[str] = Field(None, max_length=255)

class CameraUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    rtsp_url: Optional[str] = Field(None, max_length=500)
    username: Optional[str] = Field(None, max_length=100)
    password: Optional[str] = Field(None, max_length=255)
    status: Optional[CameraStatus] = None
    is_active: Optional[bool] = None
    detection_lines: Optional[List[Dict[str, Any]]] = None

class CameraResponse(CameraBase):
    id: UUID
    status: CameraStatus
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
