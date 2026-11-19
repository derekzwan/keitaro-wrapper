"""Редактор офферов: черновик в БД, публикация в Keitaro, синхронизация обратно."""

import logging
import threading
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.keitaro import KeitaroClient, KeitaroError
from app.models import ACTIVE, REMOVED, Campaign, Stream, StreamOffer
from app.services.shares import ShareError, Slot, rebalance

log = logging.getLogger(__name__)

PERIODS = {"today": "today", "yesterday": "yesterday", "7d": "7_days_ago", "30d": "1_month_ago"}
MEASURES = ("clicks", "conversions", "revenue", "profit")

_push_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)


class EditorError(ValueError):
    pass


class NotFound(LookupError):
    pass


# --- загрузка ------------------------------------------------------------


def get_campaign(db: Session, keitaro_id: int) -> Campaign | None:
    return db.scalar(select(Campaign).where(Campaign.keitaro_id == keitaro_id))


def load_campaign(db: Session, kt: KeitaroClient, keitaro_id: int) -> Campaign:
    """Кампания из БД; если её ещё нет — импортируем из Keitaro."""
    campaign = get_campaign(db, keitaro_id)
    if campaign is None:
        campaign = fetch_campaign(db, kt, keitaro_id)
    return campaign


def fetch_campaign(db: Session, kt: KeitaroClient, keitaro_id: int) -> Campaign:
    """«Fetch streams from KT»: Keitaro — источник правды, неопубликованные черновики отбрасываются."""
    try:
        kt_campaign = kt.campaign(keitaro_id)
    except KeitaroError as exc:
        if exc.status == 404:
            raise NotFound(f"Кампания {keitaro_id} не найдена в Keitaro") from exc
        raise
    campaign = get_campaign(db, keitaro_id)
    if campaign is None:
        campaign = Campaign(keitaro_id=keitaro_id, name=kt_campaign.get("name") or f"#{keitaro_id}")
        db.add(campaign)
    campaign.name = kt_campaign.get("name") or campaign.name
    campaign.alias = kt_campaign.get("alias") or campaign.alias
    if not campaign.url and kt_campaign.get("domain_id") and campaign.alias:
        domain = next((d for d in kt.domains() if d.get("id") == kt_campaign["domain_id"]), None)
        campaign.url = campaign_url(domain, campaign.alias)
    sync_campaign(db, kt, campaign)
    db.commit()
    return campaign


def get_stream(db: Session, stream_id: int) -> Stream:
    stream = db.get(Stream, stream_id)
    if stream is None:
        raise NotFound(f"Поток {stream_id} не найден")
    return stream


def get_binding(db: Session, binding_id: int) -> StreamOffer:
    row = db.get(StreamOffer, binding_id)
    if row is None:
        raise NotFound(f"Привязка {binding_id} не найдена")
    return row


# --- синхронизация с Keitaro --------------------------------------------


def campaign_url(domain: dict | None, alias: str) -> str | None:
    if not domain or not domain.get("name"):
        return None
    name = domain["name"].strip().rstrip("/")
    if "://" not in name:
        name = ("https://" if domain.get("is_ssl", True) else "http://") + name
    return f"{name}/{alias}"


def offer_preview_url(offer: dict, tracker_url: str) -> str | None:
    """Локальный оффер лежит на трекере (/lander/...), у внешнего — URL в action_payload."""
    local_path = offer.get("local_path")
    if offer.get("offer_type") == "local" and local_path and tracker_url:
        return tracker_url.rstrip("/") + "/" + local_path.lstrip("/")
    payload = offer.get("action_payload")
    if isinstance(payload, str) and payload.startswith(("http://", "https://")):
        return payload
    return None


def offer_meta(offer: dict, tracker_url: str) -> dict:
    return {
        "name": offer.get("name", ""),
        "country": ",".join(offer.get("country") or []) or None,
        "preview_url": offer_preview_url(offer, tracker_url),
    }


def _offers_meta(kt: KeitaroClient, ids: set[int]) -> dict[int, dict]:
    tracker = kt.settings.keitaro_url
    meta = {int(o["id"]): offer_meta(o, tracker) for o in kt.offers()}
    for oid in ids - meta.keys():
        # Архивные и чужие офферы не приходят в /offers — добираем поштучно.
        try:
            meta[oid] = offer_meta(kt.offer(oid), tracker)
        except KeitaroError:
            pass
    return meta


def _apply_meta(row: StreamOffer, meta: dict | None) -> None:
    if not meta:
        return
    row.offer_name = meta["name"] or row.offer_name
    row.offer_country = meta["country"]
    row.preview_url = meta["preview_url"]


def filters_summary(kt_stream: dict) -> str | None:
    parts = []
    for f in kt_stream.get("filters") or []:
        payload = f.get("payload")
        value = ", ".join(map(str, payload)) if isinstance(payload, list) else str(payload or "")
        sign = "≠" if f.get("mode") == "reject" else "="
        parts.append(f"{f.get('name')} {sign} {value}".strip())
    joiner = " ИЛИ " if kt_stream.get("filter_or") else " И "
    return joiner.join(parts) or None


def _kt_active_offers(kt_stream: dict) -> dict[int, int]:
    result: dict[int, int] = {}
    for o in kt_stream.get("offers") or []:
        if o.get("state", "active") == "active":
            result[int(o["offer_id"])] = int(o.get("share") or 0)
    return result


def apply_kt_stream(stream: Stream, kt_stream: dict, meta: dict[int, dict]) -> None:
    kt_offers = _kt_active_offers(kt_stream)
    for row in list(stream.offers):
        if row.offer_id in kt_offers:
            row.status = ACTIVE
            row.share = kt_offers.pop(row.offer_id)
        elif not row.is_published:
            stream.offers.remove(row)
            continue
        else:
            # Офферы, которых больше нет в Keitaro, не удаляем, а переводим в removed.
            row.status = REMOVED
            row.share = 0
            row.pinned = False
        _apply_meta(row, meta.get(row.offer_id))
        row.snapshot()
    for offer_id, share in kt_offers.items():
        row = StreamOffer(offer_id=offer_id, offer_name="", share=share, status=ACTIVE)
        _apply_meta(row, meta.get(offer_id))
        row.snapshot()
        stream.offers.append(row)


def sync_campaign(db: Session, kt: KeitaroClient, campaign: Campaign) -> None:
    kt_streams = kt.streams(campaign.keitaro_id)
    offer_ids = {int(o["offer_id"]) for s in kt_streams for o in (s.get("offers") or [])}
    meta = _offers_meta(kt, offer_ids) if offer_ids else {}

    existing = {s.keitaro_id: s for s in campaign.streams}
    seen: set[int] = set()
    for ks in kt_streams:
        kid = int(ks["id"])
        seen.add(kid)
        stream = existing.get(kid)
        if stream is None:
            stream = Stream(keitaro_id=kid, name="")
            campaign.streams.append(stream)
        stream.name = ks.get("name") or f"Stream #{kid}"
        stream.type = ks.get("type") or "regular"
        stream.position = int(ks.get("position") or 0)
        stream.filters_summary = filters_summary(ks)
        stream.has_offers = bool(ks.get("offers")) or bool(stream.offers)
        if stream.has_offers:
            apply_kt_stream(stream, ks, meta)
    for kid, stream in existing.items():
        if kid not in seen:
            campaign.streams.remove(stream)
    campaign.streams.sort(key=lambda s: (s.position, s.keitaro_id))
    campaign.synced_at = datetime.now(UTC)
    db.flush()


# --- операции черновика --------------------------------------------------


def _require_offer_stream(stream: Stream) -> None:
    if not stream.has_offers:
        raise EditorError("Поток без офферов не редактируется")


def _rebalance(stream: Stream) -> None:
    active = sorted(stream.active_offers, key=lambda o: o.id or 0)
    try:
        shares = rebalance([Slot(i, o.share, o.pinned) for i, o in enumerate(active)])
    except ShareError as exc:
        raise EditorError(str(exc)) from exc
    for i, o in enumerate(active):
        o.share = shares[i]
    for o in stream.offers:
        if o.status != ACTIVE:
            o.share = 0


def add_offer(db: Session, kt: KeitaroClient, stream: Stream, offer_id: int) -> StreamOffer:
    _require_offer_stream(stream)
    row = next((o for o in stream.offers if o.offer_id == offer_id), None)
    if row is not None:
        if row.status == ACTIVE:
            raise EditorError(f"Оффер {offer_id} уже в потоке")
        row.status = ACTIVE
    else:
        try:
            offer = kt.offer(offer_id)
        except KeitaroError as exc:
            if exc.status == 404:
                raise EditorError(f"Оффер {offer_id} не найден в Keitaro") from exc
            if exc.status == 403:
                raise EditorError(f"Нет доступа к офферу {offer_id} с этим API-ключом") from exc
            raise
        row = StreamOffer(offer_id=offer_id, offer_name="", share=0, status=ACTIVE)
        _apply_meta(row, offer_meta(offer, kt.settings.keitaro_url))
        stream.offers.append(row)
        db.flush()  # нужен id, чтобы новый оффер встал в конец порядка
    _rebalance(stream)
    return row


def remove_offer(db: Session, row: StreamOffer) -> None:
    stream = row.stream
    _require_offer_stream(stream)
    if row.status != ACTIVE:
        raise EditorError("Оффер уже удалён")
    if not row.is_published:
        # Черновик, который ещё не был в Keitaro, — просто выкидываем.
        stream.offers.remove(row)
        db.flush()
    else:
        row.status = REMOVED
        row.pinned = False
        row.share = 0
    _rebalance(stream)


def bring_back(row: StreamOffer) -> None:
    if row.status == ACTIVE:
        raise EditorError("Оффер и так активен")
    row.status = ACTIVE
    row.share = 0
    _rebalance(row.stream)


def set_share(row: StreamOffer, share: int) -> None:
    if row.status != ACTIVE:
        raise EditorError("Долю можно задать только активному офферу")
    if not 0 <= share <= 100:
        raise EditorError("Доля должна быть от 0 до 100")
    row.share = share
    row.pinned = True
    _rebalance(row.stream)


def set_pinned(row: StreamOffer, pinned: bool) -> None:
    if row.status != ACTIVE:
        raise EditorError("Закрепить можно только активный оффер")
    row.pinned = pinned
    if not pinned:
        _rebalance(row.stream)


def cancel(stream: Stream) -> None:
    for row in list(stream.offers):
        if not row.is_published:
            stream.offers.remove(row)
        else:
            row.revert()


def _ensure_alive_in_keitaro(kt: KeitaroClient, stream: Stream) -> None:
    """Не пишем в поток, который удалили в админке Keitaro, — иначе правки уйдут в архивный поток."""
    try:
        state = kt.stream(stream.keitaro_id).get("state")
    except KeitaroError as exc:
        if exc.status == 404:
            state = "deleted"
        else:
            raise
    if state == "deleted":
        raise EditorError("Этот поток удалён в Keitaro. Нажми «Fetch streams from KT», чтобы обновить кампанию.")


def push(db: Session, kt: KeitaroClient, stream: Stream) -> None:
    _require_offer_stream(stream)
    lock = _push_locks[stream.id]
    if not lock.acquire(blocking=False):
        raise EditorError("Поток уже публикуется")
    try:
        active = stream.active_offers
        if not active:
            raise EditorError("В потоке должен остаться хотя бы один активный оффер")
        total = sum(o.share for o in active)
        if total != 100:
            raise EditorError(f"Сумма долей {total}%, а должна быть 100%")
        _ensure_alive_in_keitaro(kt, stream)
        payload = {
            "offers": [
                {"offer_id": o.offer_id, "share": o.share, "state": "active"}
                for o in sorted(active, key=lambda o: o.id)
            ]
        }
        kt_stream = kt.update_stream(stream.keitaro_id, payload)
        if not isinstance(kt_stream, dict) or "offers" not in kt_stream:
            kt_stream = next(
                (s for s in kt.streams(stream.campaign.keitaro_id) if int(s["id"]) == stream.keitaro_id),
                None,
            )
            if kt_stream is None:
                raise EditorError("Поток пропал из Keitaro во время публикации")
        # Сверяемся с тем, что Keitaro реально сохранил.
        apply_kt_stream(stream, kt_stream, {})
        db.flush()
    finally:
        lock.release()


# --- статистика ----------------------------------------------------------


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def stats(kt: KeitaroClient, settings: Settings, campaign_kt_id: int, period: str) -> dict:
    interval = PERIODS.get(period)
    if interval is None:
        raise EditorError(f"Неизвестный период {period}")
    report = kt.report(
        {
            "range": {"interval": interval, "timezone": settings.keitaro_timezone},
            "dimensions": ["stream_id", "offer_id"],
            "measures": list(MEASURES),
            "filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": campaign_kt_id}],
        }
    )
    by_offer: dict[str, dict] = {}
    by_stream: dict[str, dict] = {}
    total = dict.fromkeys(MEASURES, 0.0)
    for r in report.get("rows") or []:
        sid = str(r.get("stream_id") or "")
        oid = str(r.get("offer_id") or "")
        values = {m: _num(r.get(m)) for m in MEASURES}
        if oid and oid != "0":
            by_offer[f"{sid}:{oid}"] = values
        bucket = by_stream.setdefault(sid, dict.fromkeys(MEASURES, 0.0))
        for m in MEASURES:
            bucket[m] += values[m]
            total[m] += values[m]
    return {"period": period, "by_offer": by_offer, "by_stream": by_stream, "total": total}


def _today(settings: Settings) -> date:
    try:
        tz = ZoneInfo(settings.keitaro_timezone)
    except Exception:
        tz = UTC
    return datetime.now(tz).date()


def trends(kt: KeitaroClient, settings: Settings, campaign_kt_id: int, days: int) -> dict:
    """Клики и конверсии по дням: для каждого оффера в потоке, для потока и для кампании."""
    if not 2 <= days <= 90:
        raise EditorError("Период трендов — от 2 до 90 дней")
    end = _today(settings)
    axis = [(end - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    index = {d: i for i, d in enumerate(axis)}
    report = kt.report(
        {
            "range": {"from": axis[0], "to": axis[-1], "timezone": settings.keitaro_timezone},
            "dimensions": ["stream_id", "offer_id", "day"],
            "measures": ["clicks", "conversions"],
            "filters": [{"name": "campaign_id", "operator": "EQUALS", "expression": campaign_kt_id}],
        }
    )

    def empty():
        return {"clicks": [0] * days, "conversions": [0] * days}

    by_offer: dict[str, dict] = {}
    by_stream: dict[str, dict] = {}
    total = empty()
    for r in report.get("rows") or []:
        i = index.get(str(r.get("day") or "")[:10])
        if i is None:
            continue
        sid = str(r.get("stream_id") or "")
        oid = str(r.get("offer_id") or "")
        targets = [by_stream.setdefault(sid, empty()), total]
        if oid and oid != "0":
            targets.append(by_offer.setdefault(f"{sid}:{oid}", empty()))
        for t in targets:
            t["clicks"][i] += int(_num(r.get("clicks")))
            t["conversions"][i] += int(_num(r.get("conversions")))
    return {"days": axis, "by_offer": by_offer, "by_stream": by_stream, "total": total}
