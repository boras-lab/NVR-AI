import uuid
import enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Enum, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .base import Base, TimestampMixin

class CameraStatus(str, enum.Enum):
    ONLINE = "Online"
    OFFLINE = "Offline"
    ERROR = "Error"

class Camera(Base, TimestampMixin):
    __tablename__ = "cameras"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    rtsp_url: Mapped[str] = mapped_column(String(500), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=True)
    password: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[CameraStatus] = mapped_column(Enum(CameraStatus), default=CameraStatus.OFFLINE, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    detection_lines: Mapped[list[dict]] = mapped_column(JSONB, default=list, nullable=False, server_default='[]')
