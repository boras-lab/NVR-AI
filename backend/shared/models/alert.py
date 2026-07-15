import uuid
import enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Enum, ForeignKey, JSON, Float, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from .base import Base, TimestampMixin

class AlertStatus(str, enum.Enum):
    NEW = "New"
    ACKNOWLEDGED = "Acknowledged"
    RESOLVED = "Resolved"

class Alert(Base, TimestampMixin):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    
    # Event category (Line Crossing, Intrusion, Object Detected)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    # Specific object (Person, Dog, Car, Smoke, Fire)
    object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    snapshot_url: Mapped[str] = mapped_column(String(500), nullable=True)
    clip_url: Mapped[str] = mapped_column(String(500), nullable=True)
    
    status: Mapped[AlertStatus] = mapped_column(Enum(AlertStatus), default=AlertStatus.NEW, nullable=False)
    
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=True) # Bounding boxes, direction, extra details
    telegram_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

