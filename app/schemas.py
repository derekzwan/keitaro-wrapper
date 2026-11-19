from datetime import UTC, datetime

from pydantic import BaseModel, Field, field_validator

from app.services.geo import parse_geo


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    geo: list[str] | str
    offer_id: int = Field(gt=0)
    domain_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    traffic_source_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Название кампании пустое")
        return v

    @field_validator("geo")
    @classmethod
    def _geo(cls, v) -> list[str]:
        return parse_geo(v)


class AddOffer(BaseModel):
    offer_id: int = Field(gt=0)


class SetShare(BaseModel):
    share: int = Field(ge=0, le=100)


class SetPinned(BaseModel):
    pinned: bool


class OfferOut(BaseModel):
    id: int
    offer_id: int
    offer_name: str
    offer_country: str | None
    preview_url: str | None
    share: int
    pinned: bool
    status: str
    is_published: bool
    is_dirty: bool
    published_share: int | None

    model_config = {"from_attributes": True}


class StreamOut(BaseModel):
    id: int
    keitaro_id: int
    name: str
    type: str
    position: int
    has_offers: bool
    filters_summary: str | None
    is_dirty: bool
    share_total: int
    offers: list[OfferOut]


class CampaignOut(BaseModel):
    id: int
    keitaro_id: int
    name: str
    alias: str | None
    url: str | None
    geo: str | None
    offer_id: int | None
    created_by_wrapper: bool
    created_at: datetime
    synced_at: datetime | None
    keitaro_link: str | None = None
    streams: list[StreamOut] = []

    @field_validator("created_at", "synced_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        # SQLite теряет tzinfo — без этого браузер прочитает UTC как локальное время.
        return v.replace(tzinfo=UTC) if v is not None and v.tzinfo is None else v


class CampaignShort(BaseModel):
    keitaro_id: int
    name: str
    alias: str | None = None
    state: str | None = None
    group_id: int | str | None = None
    in_wrapper: bool = False
    created_by_wrapper: bool = False
