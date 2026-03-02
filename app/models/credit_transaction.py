"""
CreditTransaction model: append-only credit ledger entries.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.organisation import Organisation
    from app.models.user import User


class CreditTransaction(UUIDMixin, TimestampMixin, Base):
    """Immutable credit ledger event."""

    __tablename__ = "credit_transactions"
    __table_args__ = (
        UniqueConstraint(
            "organisation_id",
            "idempotency_key",
            name="uq_credit_transactions_org_idempotency_key",
        ),
    )

    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    organisation: Mapped["Organisation"] = relationship("Organisation")
    user: Mapped["User"] = relationship("User")
