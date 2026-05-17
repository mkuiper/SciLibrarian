from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Text, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class LiteratureReview(Base):
    """Project-level generated synthesis of the library.

    Unlike Digest (which is time-windowed for "what's new"), a LiteratureReview
    summarises the corpus as a whole — themes, methods, consensus,
    disagreements, reading recommendations. New versions are generated on
    demand; older versions are kept for history.
    """
    __tablename__ = "literature_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text)  # markdown, with [id] citations
    cited_reference_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    model_used: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    ref_count_at_generation: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
