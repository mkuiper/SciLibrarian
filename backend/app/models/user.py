from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(50), default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    references: Mapped[list["Reference"]] = relationship(back_populates="created_by_user")
    collections: Mapped[list["Collection"]] = relationship(back_populates="created_by_user")
    search_monitors: Mapped[list["SearchMonitor"]] = relationship(back_populates="user")
