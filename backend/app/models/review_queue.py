from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReviewQueueItem(Base):
    __tablename__ = "review_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    source: Mapped[str] = mapped_column(String(100))
    search_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    monitor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("search_monitors.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    doi: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    arxiv_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collection_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("collections.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    monitor: Mapped[Optional["SearchMonitor"]] = relationship(back_populates="queue_items")
