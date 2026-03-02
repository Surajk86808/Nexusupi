"""
Job model for async summarisation status tracking.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.organisation import Organisation


class Job(UUIDMixin, TimestampMixin, Base):
    """Background job metadata scoped by organisation."""

    __tablename__ = "jobs"

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
    )
    result: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    organisation: Mapped["Organisation"] = relationship("Organisation")

