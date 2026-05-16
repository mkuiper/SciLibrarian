from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SearchMonitor(Base):
    __tablename__ = "search_monitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    query: Mapped[str] = mapped_column(Text)
    sources: Mapped[str] = mapped_column(String(500), default="arxiv,semantic_scholar")
    frequency: Mapped[str] = mapped_column(String(50), default="weekly")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approve_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reject_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    negative_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="search_monitors")
    queue_items: Mapped[list["ReviewQueueItem"]] = relationship(back_populates="monitor")
