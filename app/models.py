from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ACTIVE = "active"
REMOVED = "removed"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    alias: Mapped[str | None] = mapped_column(String(64))
    url: Mapped[str | None] = mapped_column(String(512))
    # Заполняются только для кампаний, созданных через создаватор.
    geo: Mapped[str | None] = mapped_column(String(255))
    offer_id: Mapped[int | None] = mapped_column(Integer)
    created_by_wrapper: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    streams: Mapped[list["Stream"]] = relationship(
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="Stream.position",
    )


class Stream(Base):
    __tablename__ = "streams"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    keitaro_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[str] = mapped_column(String(32), default="regular")
    position: Mapped[int] = mapped_column(Integer, default=0)
    # Поток без офферов показываем как есть и не разбираем его содержимое.
    has_offers: Mapped[bool] = mapped_column(Boolean, default=False)
    filters_summary: Mapped[str | None] = mapped_column(String(512))

    campaign: Mapped[Campaign] = relationship(back_populates="streams")
    offers: Mapped[list["StreamOffer"]] = relationship(
        back_populates="stream",
        cascade="all, delete-orphan",
        order_by="StreamOffer.id",
    )

    @property
    def is_dirty(self) -> bool:
        return any(o.is_dirty for o in self.offers)

    @property
    def active_offers(self) -> list["StreamOffer"]:
        return [o for o in self.offers if o.status == ACTIVE]


class StreamOffer(Base):
    """Привязка оффера к потоку: текущий черновик + снимок того, что опубликовано в Keitaro."""

    __tablename__ = "stream_offers"
    __table_args__ = (UniqueConstraint("stream_id", "offer_id", name="uq_stream_offer"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id", ondelete="CASCADE"), index=True)
    offer_id: Mapped[int] = mapped_column(Integer)
    offer_name: Mapped[str] = mapped_column(String(512), default="")
    offer_country: Mapped[str | None] = mapped_column(String(128))
    preview_url: Mapped[str | None] = mapped_column(String(1024))

    share: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(16), default=ACTIVE)

    # None в published_status — привязка добавлена в обёртке и ещё не уходила в Keitaro.
    published_share: Mapped[int | None] = mapped_column(Integer)
    published_pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    published_status: Mapped[str | None] = mapped_column(String(16))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    stream: Mapped[Stream] = relationship(back_populates="offers")

    @property
    def is_published(self) -> bool:
        return self.published_status is not None

    @property
    def is_dirty(self) -> bool:
        return (
            self.published_status is None
            or self.status != self.published_status
            or self.share != self.published_share
            or self.pinned != self.published_pinned
        )

    def snapshot(self) -> None:
        self.published_share = self.share
        self.published_pinned = self.pinned
        self.published_status = self.status

    def revert(self) -> None:
        self.share = self.published_share or 0
        self.pinned = self.published_pinned
        self.status = self.published_status or REMOVED
