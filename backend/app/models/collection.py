from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Collection(Base):
    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("collections.id"), nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    path: Mapped[str] = mapped_column(String(1000), default="/")
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parent: Mapped[Optional["Collection"]] = relationship("Collection", remote_side="Collection.id", back_populates="children")
    children: Mapped[list["Collection"]] = relationship("Collection", back_populates="parent")
    references: Mapped[list["Reference"]] = relationship(back_populates="collection")
    created_by_user: Mapped["User"] = relationship(back_populates="collections")
    project: Mapped[Optional["Project"]] = relationship(back_populates="collections")
