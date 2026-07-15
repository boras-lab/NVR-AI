import uuid
import enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Enum, ForeignKey, Integer, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
from .base import Base, TimestampMixin

class FaceTag(str, enum.Enum):
    UNKNOWN = "Unknown"
    EMPLOYEE = "Employee"
    VISITOR = "Visitor"
    BLACKLISTED = "Blacklisted"

class Face(Base, TimestampMixin):
    __tablename__ = "faces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    person_name: Mapped[str] = mapped_column(String(200), nullable=True)
    is_known: Mapped[bool] = mapped_column(default=False, nullable=False)
    
    similarity_score: Mapped[float] = mapped_column(Float, nullable=True)
    
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    visit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    camera_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True)
    photo_url: Mapped[str] = mapped_column(String(500), nullable=True)
    
    tag: Mapped[FaceTag] = mapped_column(Enum(FaceTag), default=FaceTag.UNKNOWN, nullable=False)
