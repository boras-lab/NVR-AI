import uuid
import enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Enum, ForeignKey, JSON
from sqlalchemy.dialects.postgresql import UUID
from .base import Base, TimestampMixin

class EventCategory(str, enum.Enum):
    SYSTEM = "System"
    AUTH = "Auth"
    CAMERA = "Camera"
    AI = "AI"
    DATABASE = "Database"
    ALERT = "Alert"

class EventSeverity(str, enum.Enum):
    INFO = "Info"
    WARNING = "Warning"
    ERROR = "Error"
    CRITICAL = "Critical"

class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category: Mapped[EventCategory] = mapped_column(Enum(EventCategory), nullable=False)
    severity: Mapped[EventSeverity] = mapped_column(Enum(EventSeverity), default=EventSeverity.INFO, nullable=False)
    
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    
    # Optional foreign keys for context
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=True)
