"""In-memory имитация Keitaro Admin API v1 — для тестов и офлайн-демо.

Запуск: uv run uvicorn tests.fake_keitaro:app --port 8090
"""

import itertools
from datetime import date, timedelta
from contextlib import asynccontextmanager
import zlib

from fastapi import APIRouter, FastAPI, Header, HTTPException, Request

API_KEY = "test-key"


class State:
    def __init__(self):
        self.ids = itertools.count(100)
        self.domains = [
            {"id": 1, "name": "in.posdk.xyz", "state": "active", "is_ssl": True},
            {"id": 2, "name": "old.example.com", "state": "deleted", "is_ssl": True},
        ]
        self.groups = [{"id": 7, "name": "FORTESTS", "type": "campaigns"}, {"id": 8, "name": "MAIN", "type": "campaigns"}]
        self.sources = [{"id": 3, "name": "FORTESTS", "state": "active"}, {"id": 4, "name": "Facebook", "state": "active"}]
        self.offers = {
            3749: {"id": 3749, "name": "Miaflow [BEAUTY-RO-BE_0009] [pl - spin ro -] 2. Основной, Румыния JS", "state": "active", "country": ["RO"], "offer_type": "local", "local_path": "/lander/miaflow_spin/"},
            3717: {"id": 3717, "name": "Miaflow [BEAUTY-RO-BE_0008] [pl - prize ro -] 1. Основной, Румыния JS", "state": "active", "country": ["RO"]},
            11111: {"id": 11111, "name": "FitoMishki [Weight Loss-CO-DT_0309] [pl es -]", "state": "active", "country": ["CO"], "offer_type": "external", "action_payload": "https://fito.example/?sub={subid}"},
            11112: {"id": 11112, "name": "Oxys [BEAUTY-CL-BE_0155] [pl es -]", "state": "active", "country": ["CL"]},
            5001: {"id": 5001, "name": "Archived [OLD-MX_0001]", "state": "deleted", "country": ["MX"]},
        }
        self.campaigns: dict[int, dict] = {}
        self.streams: dict[int, dict] = {}
        self.fail_next_stream = False

    def seed_demo(self):
        """Кампания как в видео: Flow 1 (AU → Google) и Flow 2 с тремя офферами."""
        cid = self.add_campaign({"name": "campaign 2", "alias": "wVqN1R", "domain_id": 1, "group_id": 7, "traffic_source_id": 3})
        self.add_stream({"campaign_id": cid, "name": "Flow 1", "type": "regular", "position": 1, "schema": "redirect",
                         "action_type": "http", "action_payload": "https://google.com",
                         "filters": [{"name": "country", "mode": "accept", "payload": ["AU"]}]})
        self.add_stream({"campaign_id": cid, "name": "Flow 2", "type": "regular", "position": 2, "schema": "landings",
                         "action_type": "http", "offers": [{"offer_id": 3749, "share": 33}, {"offer_id": 3717, "share": 33},
                                                           {"offer_id": 11111, "share": 34}]})
        return cid

    def add_campaign(self, body: dict) -> int:
        cid = next(self.ids)
        self.campaigns[cid] = {"id": cid, "state": "active", "type": "position", **body}
        return cid

    def add_stream(self, body: dict) -> dict:
        sid = next(self.ids)
        offers = [
            {"id": next(self.ids), "stream_id": sid, "offer_id": int(o["offer_id"]), "share": int(o["share"]),
             "state": o.get("state", "active")}
            for o in body.get("offers") or []
        ]
        stream = {"id": sid, "state": "active", "filters": [], "landings": [], **body, "offers": offers}
        self.streams[sid] = stream
        return stream


state = State()
router = APIRouter(prefix="/admin_api/v1")


def auth(api_key: str | None):
    if api_key != API_KEY:
        raise HTTPException(401, "Unauthorized")


def _404(what: str):
    raise HTTPException(404, {"error": f"{what} not found"})


@router.get("/domains")
def domains(api_key: str | None = Header(None)):
    auth(api_key)
    return state.domains


@router.get("/groups")
def groups(type: str, api_key: str | None = Header(None)):
    auth(api_key)
    return [g for g in state.groups if g["type"] == type]


@router.get("/traffic_sources")
def sources(api_key: str | None = Header(None)):
    auth(api_key)
    return state.sources


@router.get("/offers")
def offers(api_key: str | None = Header(None)):
    auth(api_key)
    return list(state.offers.values())


@router.get("/offers/{offer_id}")
def offer(offer_id: int, api_key: str | None = Header(None)):
    auth(api_key)
    return state.offers.get(offer_id) or _404("offer")


@router.get("/campaigns")
def campaigns(api_key: str | None = Header(None)):
    auth(api_key)
    return list(state.campaigns.values())


@router.get("/campaigns/{cid}")
def campaign(cid: int, api_key: str | None = Header(None)):
    auth(api_key)
    return state.campaigns.get(cid) or _404("campaign")


@router.post("/campaigns")
async def create_campaign(request: Request, api_key: str | None = Header(None)):
    auth(api_key)
    body = await request.json()
    for field in ("name", "alias"):
        if not body.get(field):
            raise HTTPException(400, {"error": f"{field} is required"})
    return state.campaigns[state.add_campaign(body)]


@router.delete("/campaigns/{cid}")
def delete_campaign(cid: int, api_key: str | None = Header(None)):
    auth(api_key)
    c = state.campaigns.get(cid) or _404("campaign")
    c["state"] = "deleted"
    return c


@router.get("/campaigns/{cid}/streams")
def campaign_streams(cid: int, api_key: str | None = Header(None)):
    auth(api_key)
    return sorted((s for s in state.streams.values() if s["campaign_id"] == cid and s.get("state") != "deleted"),
                  key=lambda s: s.get("position", 0))


@router.post("/streams")
async def create_stream(request: Request, api_key: str | None = Header(None)):
    auth(api_key)
    if state.fail_next_stream:
        state.fail_next_stream = False
        raise HTTPException(500, {"error": "boom"})
    body = await request.json()
    for field in ("campaign_id", "schema", "type", "name", "action_type"):
        if field not in body:
            raise HTTPException(400, {"error": f"{field} is required"})
    if body["campaign_id"] not in state.campaigns:
        _404("campaign")
    return state.add_stream(body)


@router.get("/streams/{sid}")
def get_stream(sid: int, api_key: str | None = Header(None)):
    auth(api_key)
    return state.streams.get(sid) or _404("stream")


@router.delete("/streams/{sid}")
def delete_stream(sid: int, api_key: str | None = Header(None)):
    auth(api_key)
    stream = state.streams.get(sid) or _404("stream")
    stream["state"] = "deleted"
    return stream


@router.put("/streams/{sid}")
async def update_stream(sid: int, request: Request, api_key: str | None = Header(None)):
    auth(api_key)
    stream = state.streams.get(sid) or _404("stream")
    body = await request.json()
    if "offers" in body:
        if sum(int(o["share"]) for o in body["offers"]) != 100:
            raise HTTPException(400, {"error": "shares must sum to 100"})
        stream["offers"] = [
            {"id": next(state.ids), "stream_id": sid, "offer_id": int(o["offer_id"]), "share": int(o["share"]),
             "state": o.get("state", "active")}
            for o in body["offers"]
        ]
    stream.update({k: v for k, v in body.items() if k != "offers"})
    return stream


@router.post("/report/build")
async def report(request: Request, api_key: str | None = Header(None)):
    auth(api_key)
    body = await request.json()
    cid = next(f["expression"] for f in body["filters"] if f["name"] == "campaign_id")
    rng = body["range"]
    if "from" in rng:
        start, end = date.fromisoformat(rng["from"]), date.fromisoformat(rng["to"])
        days = [(start + timedelta(d)).isoformat() for d in range((end - start).days + 1)]
        mult = 1
    else:
        days = None
        mult = {"today": 1, "yesterday": 1, "7_days_ago": 7, "1_month_ago": 30}.get(rng.get("interval"), 1)
    by_day = "day" in body["dimensions"]
    rows = []
    for s in state.streams.values():
        if s["campaign_id"] != cid:
            continue
        targets = [o["offer_id"] for o in s["offers"]] or [None]
        for oid in targets:
            seed = zlib.crc32(f"{s['id']}:{oid}".encode()) % 97
            clicks = (seed + 3) * mult
            conv = clicks // 23
            revenue = round(conv * 18.5, 2)
            row = {"stream_id": s["id"], "offer_id": oid, "clicks": clicks, "conversions": conv,
                   "revenue": revenue, "profit": round(revenue - clicks * 0.12, 2)}
            if by_day and days:
                for i, d in enumerate(days):
                    c = (seed + i * 7) % 40
                    rows.append({"stream_id": s["id"], "offer_id": oid or 0, "day": d, "clicks": c, "conversions": c // 15})
            else:
                rows.append(row)
    return {"rows": rows, "total": len(rows)}


@asynccontextmanager
async def lifespan(_):
    if not state.campaigns:
        state.seed_demo()
    yield


app = FastAPI(title="Fake Keitaro", lifespan=lifespan)
app.include_router(router)
