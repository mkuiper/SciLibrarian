from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, JSON, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Reference(Base):
    __tablename__ = "references"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    authors: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="paper")
    abstract: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(2000), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    collection_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("collections.id"), nullable=True)
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    extra_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    collection: Mapped[Optional["Collection"]] = relationship(back_populates="references")
    project: Mapped[Optional["Project"]] = relationship(back_populates="references")
    created_by_user: Mapped["User"] = relationship(back_populates="references")
    tags: Mapped[list["ReferenceTag"]] = relationship(back_populates="reference", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_references_collection_id", "collection_id"),
        Index("ix_references_source_type", "source_type"),
        Index("ix_references_year", "year"),
    )


class ReferenceTag(Base):
    __tablename__ = "reference_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(Integer, ForeignKey("references.id"))
    tag: Mapped[str] = mapped_column(String(100), index=True)

    reference: Mapped["Reference"] = relationship(back_populates="tags")
