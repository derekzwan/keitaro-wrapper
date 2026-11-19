"""Создаватор: кампания + поток «гео → Google» + поток «на оффер»."""

import logging
import secrets
import string

from sqlalchemy.orm import Session

from app.config import Settings
from app.keitaro import KeitaroClient, KeitaroError
from app.models import Campaign
from app.services import editor
from app.services.editor import campaign_url

log = logging.getLogger(__name__)

_ALIAS_ALPHABET = string.ascii_letters + string.digits


class CreateError(ValueError):
    pass


def make_alias(length: int = 7) -> str:
    return "".join(secrets.choice(_ALIAS_ALPHABET) for _ in range(length))


def _find(items: list[dict], item_id, label: str) -> dict:
    for item in items:
        if str(item.get("id")) == str(item_id):
            return item
    raise CreateError(f"{label} с id={item_id} не найден в Keitaro")


def build_geo_stream(campaign_id: int, geo: list[str], google_url: str) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": "Flow 1",
        "position": 1,
        "state": "active",
        "schema": "redirect",
        "action_type": "http",
        "action_payload": google_url,
        "collect_clicks": True,
        "filter_or": False,
        "filters": [{"name": "country", "mode": "accept", "payload": geo}],
    }


def build_offer_stream(campaign_id: int, offer_id: int) -> dict:
    return {
        "campaign_id": campaign_id,
        "type": "regular",
        "name": "Flow 2",
        "position": 2,
        "state": "active",
        "schema": "landings",
        "action_type": "http",
        "collect_clicks": True,
        "filter_or": False,
        "filters": [],
        "landings": [],
        "offers": [{"offer_id": offer_id, "share": 100, "state": "active"}],
    }


def create_campaign(
    db: Session,
    kt: KeitaroClient,
    settings: Settings,
    *,
    name: str,
    geo: list[str],
    offer_id: int,
    domain_id: int,
    group_id: int | str,
    traffic_source_id: int,
) -> Campaign:
    name = name.strip()
    if not name:
        raise CreateError("Название кампании пустое")

    # Проверяем всё до первого POST, чтобы не плодить мусор в трекере.
    try:
        kt.offer(offer_id)
    except KeitaroError as exc:
        if exc.status == 404:
            raise CreateError(f"Оффер {offer_id} не найден в Keitaro") from exc
        if exc.status == 403:
            raise CreateError(f"Нет доступа к офферу {offer_id} с этим API-ключом") from exc
        raise
    domain = _find(kt.domains(), domain_id, "Домен")
    _find(kt.groups("campaigns"), group_id, "Группа")
    _find(kt.traffic_sources(), traffic_source_id, "Источник")

    alias = make_alias()
    kt_campaign = kt.create_campaign(
        {
            "name": name,
            "alias": alias,
            "type": "position",
            "state": "active",
            "cost_type": "CPC",
            "domain_id": int(domain_id),
            "group_id": group_id,
            "traffic_source_id": int(traffic_source_id),
        }
    )
    kt_id = int(kt_campaign["id"])
    alias = kt_campaign.get("alias") or alias

    try:
        kt.create_stream(build_geo_stream(kt_id, geo, settings.google_url))
        kt.create_stream(build_offer_stream(kt_id, offer_id))
    except KeitaroError:
        # Компенсация: кампания без потоков никому не нужна.
        try:
            kt.delete_campaign(kt_id)
        except KeitaroError as cleanup_exc:
            log.error("не удалось откатить кампанию %s: %s", kt_id, cleanup_exc)
        raise

    campaign = Campaign(
        keitaro_id=kt_id,
        name=name,
        alias=alias,
        url=campaign_url(domain, alias),
        geo=",".join(geo),
        offer_id=offer_id,
        created_by_wrapper=True,
    )
    db.add(campaign)
    db.flush()
    editor.sync_campaign(db, kt, campaign)
    db.commit()
    return campaign
