from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import get_db
from app.keitaro import KeitaroClient, KeitaroError, get_keitaro
from app.models import ACTIVE, Campaign, Stream
from app.schemas import (
    AddOffer,
    CampaignCreate,
    CampaignOut,
    CampaignShort,
    OfferOut,
    SetPinned,
    SetShare,
    StreamOut,
)
from app.services import creator, editor

router = APIRouter(prefix="/api")


def kt_dep() -> KeitaroClient:
    try:
        return get_keitaro()
    except KeitaroError as exc:
        raise HTTPException(503, exc.message) from exc


# --- сериализация --------------------------------------------------------


def stream_out(stream: Stream) -> StreamOut:
    offers = sorted(stream.offers, key=lambda o: (o.status != ACTIVE, o.id))
    return StreamOut(
        id=stream.id,
        keitaro_id=stream.keitaro_id,
        name=stream.name,
        type=stream.type,
        position=stream.position,
        has_offers=stream.has_offers,
        filters_summary=stream.filters_summary,
        is_dirty=stream.is_dirty,
        share_total=sum(o.share for o in stream.active_offers),
        offers=[OfferOut.model_validate(o) for o in offers],
    )


def campaign_out(campaign: Campaign, settings: Settings, with_streams: bool = True) -> CampaignOut:
    link = f"{settings.keitaro_admin_base}#!/campaign/{campaign.keitaro_id}/main" if settings.keitaro_url else None
    return CampaignOut(
        id=campaign.id,
        keitaro_id=campaign.keitaro_id,
        name=campaign.name,
        alias=campaign.alias,
        url=campaign.url,
        geo=campaign.geo,
        offer_id=campaign.offer_id,
        created_by_wrapper=campaign.created_by_wrapper,
        created_at=campaign.created_at,
        synced_at=campaign.synced_at,
        keitaro_link=link,
        streams=[stream_out(s) for s in campaign.streams] if with_streams else [],
    )


def run_edit(db: Session, fn: Callable[[], object]) -> None:
    """Операция редактора атомарна: ошибка — откат черновика целиком."""
    try:
        fn()
        db.commit()
    except editor.EditorError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except editor.NotFound as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except KeitaroError as exc:
        db.rollback()
        raise HTTPException(502, exc.message) from exc
    except Exception:
        db.rollback()
        raise


def _found(fn):
    try:
        return fn()
    except editor.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except KeitaroError as exc:
        raise HTTPException(502, exc.message) from exc


# --- справочники ---------------------------------------------------------


def _pick_default(items: list[dict], wanted: str):
    wanted = wanted.strip().lower()
    for item in items:
        name = str(item.get("name", "")).lower().rstrip("/")
        if wanted and (name == wanted or name.split("://")[-1] == wanted.split("://")[-1].rstrip("/")):
            return item["id"]
    return items[0]["id"] if items else None


@router.get("/meta")
def meta(kt: KeitaroClient = Depends(kt_dep), settings: Settings = Depends(get_settings)):
    def load():
        domains = [{"id": d["id"], "name": d["name"]} for d in kt.domains()]
        groups = [{"id": g["id"], "name": g["name"]} for g in kt.groups("campaigns")]
        sources = [{"id": s["id"], "name": s["name"]} for s in kt.traffic_sources()]
        return {
            "domains": domains,
            "groups": groups,
            "sources": sources,
            "defaults": {
                "domain_id": _pick_default(domains, settings.default_domain),
                "group_id": _pick_default(groups, settings.default_group),
                "traffic_source_id": _pick_default(sources, settings.default_source),
            },
            "google_url": settings.google_url,
            "keitaro_url": settings.keitaro_url,
        }

    return _found(load)


@router.get("/offers")
def search_offers(q: str = "", limit: int = Query(20, ge=1, le=500), kt: KeitaroClient = Depends(kt_dep)):
    offers = _found(kt.offers)
    q = q.strip().lower()
    result = []
    for o in offers:
        oid, name = str(o["id"]), str(o.get("name", ""))
        if not q or oid.startswith(q) or q in name.lower():
            meta = editor.offer_meta(o, kt.settings.keitaro_url)
            result.append({
                "id": o["id"],
                "name": name,
                "country": meta["country"],
                "preview_url": meta["preview_url"],
                "group": o.get("group") or None,
                "payout": f'{o.get("payout_value") or 0} {o.get("payout_currency") or ""} {o.get("payout_type") or ""}'.strip(),
            })
    # Точное совпадение по id — первым.
    result.sort(key=lambda o: (str(o["id"]) != q, -int(o["id"])))
    return result[:limit]


# --- создаватор ----------------------------------------------------------


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(
    body: CampaignCreate,
    db: Session = Depends(get_db),
    kt: KeitaroClient = Depends(kt_dep),
    settings: Settings = Depends(get_settings),
):
    try:
        campaign = creator.create_campaign(
            db,
            kt,
            settings,
            name=body.name,
            geo=body.geo,
            offer_id=body.offer_id,
            domain_id=body.domain_id,
            group_id=body.group_id,
            traffic_source_id=body.traffic_source_id,
        )
    except creator.CreateError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except KeitaroError as exc:
        db.rollback()
        raise HTTPException(502, exc.message) from exc
    return campaign_out(campaign, settings)


@router.get("/campaigns/recent", response_model=list[CampaignOut])
def recent_campaigns(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    rows = db.scalars(
        select(Campaign).where(Campaign.created_by_wrapper.is_(True)).order_by(Campaign.created_at.desc()).limit(10)
    )
    return [campaign_out(c, settings, with_streams=False) for c in rows]


# --- редактор ------------------------------------------------------------


@router.get("/campaigns", response_model=list[CampaignShort])
def list_campaigns(db: Session = Depends(get_db), kt: KeitaroClient = Depends(kt_dep)):
    kt_campaigns = _found(kt.campaigns)
    local = {c.keitaro_id: c for c in db.scalars(select(Campaign))}
    result = []
    for c in sorted(kt_campaigns, key=lambda c: -int(c["id"])):
        mine = local.get(int(c["id"]))
        result.append(
            CampaignShort(
                keitaro_id=int(c["id"]),
                name=c.get("name", ""),
                alias=c.get("alias"),
                state=c.get("state"),
                group_id=c.get("group_id"),
                in_wrapper=mine is not None,
                created_by_wrapper=bool(mine and mine.created_by_wrapper),
            )
        )
    return result


@router.get("/campaigns/{keitaro_id}", response_model=CampaignOut)
def get_campaign(
    keitaro_id: int,
    db: Session = Depends(get_db),
    kt: KeitaroClient = Depends(kt_dep),
    settings: Settings = Depends(get_settings),
):
    campaign = _found(lambda: editor.load_campaign(db, kt, keitaro_id))
    return campaign_out(campaign, settings)


@router.post("/campaigns/{keitaro_id}/fetch", response_model=CampaignOut)
def fetch_campaign(
    keitaro_id: int,
    db: Session = Depends(get_db),
    kt: KeitaroClient = Depends(kt_dep),
    settings: Settings = Depends(get_settings),
):
    campaign = None

    def op():
        nonlocal campaign
        campaign = editor.fetch_campaign(db, kt, keitaro_id)

    run_edit(db, op)
    return campaign_out(campaign, settings)


@router.get("/campaigns/{keitaro_id}/stats")
def campaign_stats(
    keitaro_id: int,
    period: str = "today",
    kt: KeitaroClient = Depends(kt_dep),
    settings: Settings = Depends(get_settings),
):
    try:
        return editor.stats(kt, settings, keitaro_id, period)
    except editor.EditorError as exc:
        raise HTTPException(422, str(exc)) from exc
    except KeitaroError as exc:
        raise HTTPException(502, exc.message) from exc


@router.get("/campaigns/{keitaro_id}/trends")
def campaign_trends(
    keitaro_id: int,
    days: int = Query(14, ge=2, le=90),
    kt: KeitaroClient = Depends(kt_dep),
    settings: Settings = Depends(get_settings),
):
    try:
        return editor.trends(kt, settings, keitaro_id, days)
    except editor.EditorError as exc:
        raise HTTPException(422, str(exc)) from exc
    except KeitaroError as exc:
        raise HTTPException(502, exc.message) from exc


def _stream_action(db: Session, stream_id: int, action: Callable[[Stream], object]) -> StreamOut:
    stream = _found(lambda: editor.get_stream(db, stream_id))
    run_edit(db, lambda: action(stream))
    db.refresh(stream)
    return stream_out(stream)


def _offer_action(db: Session, binding_id: int, action: Callable) -> StreamOut:
    row = _found(lambda: editor.get_binding(db, binding_id))
    stream_id = row.stream_id
    run_edit(db, lambda: action(row))
    return stream_out(editor.get_stream(db, stream_id))


@router.post("/streams/{stream_id}/offers", response_model=StreamOut)
def add_offer(stream_id: int, body: AddOffer, db: Session = Depends(get_db), kt: KeitaroClient = Depends(kt_dep)):
    return _stream_action(db, stream_id, lambda s: editor.add_offer(db, kt, s, body.offer_id))


@router.post("/streams/{stream_id}/push", response_model=StreamOut)
def push_stream(stream_id: int, db: Session = Depends(get_db), kt: KeitaroClient = Depends(kt_dep)):
    return _stream_action(db, stream_id, lambda s: editor.push(db, kt, s))


@router.post("/streams/{stream_id}/cancel", response_model=StreamOut)
def cancel_stream(stream_id: int, db: Session = Depends(get_db)):
    return _stream_action(db, stream_id, editor.cancel)


@router.post("/stream-offers/{binding_id}/remove", response_model=StreamOut)
def remove_offer(binding_id: int, db: Session = Depends(get_db)):
    return _offer_action(db, binding_id, lambda r: editor.remove_offer(db, r))


@router.post("/stream-offers/{binding_id}/restore", response_model=StreamOut)
def bring_back(binding_id: int, db: Session = Depends(get_db)):
    return _offer_action(db, binding_id, editor.bring_back)


@router.put("/stream-offers/{binding_id}/share", response_model=StreamOut)
def set_share(binding_id: int, body: SetShare, db: Session = Depends(get_db)):
    return _offer_action(db, binding_id, lambda r: editor.set_share(r, body.share))


@router.put("/stream-offers/{binding_id}/pin", response_model=StreamOut)
def set_pinned(binding_id: int, body: SetPinned, db: Session = Depends(get_db)):
    return _offer_action(db, binding_id, lambda r: editor.set_pinned(r, body.pinned))
