"""Сценарии из ТЗ и видео: создаватор и редактор через HTTP API против фейкового Keitaro."""


def kt_stream(fake, sid):
    return fake.streams[sid]


def kt_offers(fake, sid):
    return {o["offer_id"]: o["share"] for o in fake.streams[sid]["offers"]}


def offer_stream(campaign):
    return next(s for s in campaign["streams"] if s["has_offers"])


def by_offer(stream):
    return {o["offer_id"]: o for o in stream["offers"]}


# --- создаватор ----------------------------------------------------------


CREATE = {"name": "RO test", "geo": "AU, mx", "offer_id": 3749, "domain_id": 1, "group_id": 7, "traffic_source_id": 3}


def test_create_campaign_builds_two_streams(api, fake):
    r = api.post("/api/campaigns", json=CREATE)
    assert r.status_code == 201, r.text
    c = r.json()
    kt_c = fake.campaigns[c["keitaro_id"]]
    assert kt_c["domain_id"] == 1 and kt_c["group_id"] == 7 and kt_c["traffic_source_id"] == 3
    assert kt_c["type"] == "position"
    assert c["url"] == f"https://in.posdk.xyz/{kt_c['alias']}"

    geo, offers = sorted((s for s in fake.streams.values() if s["campaign_id"] == c["keitaro_id"]),
                         key=lambda s: s["position"])
    assert geo["schema"] == "redirect" and geo["action_payload"] == "https://google.com"
    assert geo["filters"] == [{"name": "country", "mode": "accept", "payload": ["AU", "MX"]}]
    assert offers["schema"] == "landings" and kt_offers(fake, offers["id"]) == {3749: 100}

    # Локально: поток без офферов + поток с одним оффером 100%
    assert [s["has_offers"] for s in c["streams"]] == [False, True]
    assert offer_stream(c)["offers"][0]["share"] == 100


def test_create_validates_before_touching_keitaro(api, fake):
    assert api.post("/api/campaigns", json={**CREATE, "geo": "ZZ"}).status_code == 422
    r = api.post("/api/campaigns", json={**CREATE, "offer_id": 999999})
    assert r.status_code == 422 and "не найден" in r.json()["detail"]
    assert api.post("/api/campaigns", json={**CREATE, "domain_id": 2}).status_code == 422  # домен в архиве
    assert fake.campaigns == {}


def test_create_rolls_back_campaign_when_stream_fails(api, fake):
    fake.fail_next_stream = True
    r = api.post("/api/campaigns", json=CREATE)
    assert r.status_code == 502
    (c,) = fake.campaigns.values()
    assert c["state"] == "deleted"
    assert api.get("/api/campaigns/recent").json() == []


def test_offer_search(api):
    found = api.get("/api/offers", params={"q": "miaflow"}).json()
    assert {o["id"] for o in found} == {3749, 3717}
    assert api.get("/api/offers", params={"q": "11112"}).json()[0]["id"] == 11112
    assert all(o["id"] != 5001 for o in api.get("/api/offers").json())  # архивные не предлагаем


# --- редактор ------------------------------------------------------------


def open_demo(api, fake):
    cid = fake.seed_demo()
    c = api.post(f"/api/campaigns/{cid}/fetch").json()
    return cid, c


def test_fetch_parses_only_offer_streams(api, fake):
    _, c = open_demo(api, fake)
    flow1, flow2 = c["streams"]
    assert flow1["name"] == "Flow 1" and not flow1["has_offers"] and flow1["offers"] == []
    assert [o["share"] for o in flow2["offers"]] == [33, 33, 34]
    assert not flow2["is_dirty"]


def test_add_offer_rebalances_and_push(api, fake):
    _, c = open_demo(api, fake)
    s = offer_stream(c)
    r = api.post(f"/api/streams/{s['id']}/offers", json={"offer_id": 11112})
    s = r.json()
    assert [o["share"] for o in s["offers"]] == [25, 25, 25, 25]
    assert s["is_dirty"]
    assert len(kt_offers(fake, s["keitaro_id"])) == 3  # до push в Keitaro ничего не изменилось

    s = api.post(f"/api/streams/{s['id']}/push").json()
    assert not s["is_dirty"]
    assert kt_offers(fake, s["keitaro_id"]) == {3749: 25, 3717: 25, 11111: 25, 11112: 25}


def test_cancel_drops_unpublished_offers(api, fake):
    _, c = open_demo(api, fake)
    s = offer_stream(c)
    api.post(f"/api/streams/{s['id']}/offers", json={"offer_id": 11112})
    s = api.post(f"/api/streams/{s['id']}/cancel").json()
    assert not s["is_dirty"]
    assert {o["offer_id"]: o["share"] for o in s["offers"]} == {3749: 33, 3717: 33, 11111: 34}


def test_remove_then_bring_back(api, fake):
    _, c = open_demo(api, fake)
    s = offer_stream(c)
    target = by_offer(s)[11111]["id"]
    s = api.post(f"/api/stream-offers/{target}/remove").json()
    o = by_offer(s)
    assert o[11111]["status"] == "removed" and o[11111]["share"] == 0
    assert o[3749]["share"] + o[3717]["share"] == 100 and s["is_dirty"]

    s = api.post(f"/api/streams/{s['id']}/push").json()
    assert 11111 not in kt_offers(fake, s["keitaro_id"])
    assert by_offer(s)[11111]["status"] == "removed"  # остался в архиве обёртки

    s = api.post(f"/api/stream-offers/{target}/restore").json()
    assert by_offer(s)[11111]["status"] == "active" and s["is_dirty"]
    api.post(f"/api/streams/{s['id']}/push")
    assert kt_offers(fake, s["keitaro_id"]) == {3749: 34, 3717: 33, 11111: 33}


def test_removed_in_keitaro_becomes_removed_on_fetch(api, fake):
    cid, c = open_demo(api, fake)
    s = offer_stream(c)
    kt_stream(fake, s["keitaro_id"])["offers"] = [{"offer_id": 3749, "share": 100, "state": "active"}]
    c = api.post(f"/api/campaigns/{cid}/fetch").json()
    o = by_offer(offer_stream(c))
    assert o[3749]["share"] == 100 and o[3749]["status"] == "active"
    assert o[3717]["status"] == "removed" and o[11111]["status"] == "removed"
    assert not offer_stream(c)["is_dirty"]


def test_pinned_share_survives_operations(api, fake):
    _, c = open_demo(api, fake)
    s = offer_stream(c)
    api.post(f"/api/streams/{s['id']}/offers", json={"offer_id": 11112})  # 25 x4
    o = by_offer(api.get(f"/api/campaigns/{c['keitaro_id']}").json()["streams"][1])
    api.put(f"/api/stream-offers/{o[3717]['id']}/pin", json={"pinned": True})
    s = api.post(f"/api/stream-offers/{o[11111]['id']}/remove").json()
    shares = {x["offer_id"]: x["share"] for x in s["offers"] if x["status"] == "active"}
    assert shares == {3749: 38, 3717: 25, 11112: 37}

    s = api.post(f"/api/streams/{s['id']}/push").json()
    assert kt_offers(fake, s["keitaro_id"]) == {3749: 38, 3717: 25, 11112: 37}
    assert by_offer(s)[3717]["pinned"]


def test_manual_share_pins_and_rebalances(api, fake):
    _, c = open_demo(api, fake)
    s = offer_stream(c)
    oid = by_offer(s)[3749]["id"]
    s = api.put(f"/api/stream-offers/{oid}/share", json={"share": 50}).json()
    o = by_offer(s)
    assert o[3749]["pinned"] and o[3749]["share"] == 50
    assert o[3717]["share"] == 25 and o[11111]["share"] == 25


def test_invalid_operation_rolls_back(api, fake):
    _, c = open_demo(api, fake)
    s = offer_stream(c)
    o = by_offer(s)
    api.put(f"/api/stream-offers/{o[3749]['id']}/share", json={"share": 60})
    api.put(f"/api/stream-offers/{o[3717]['id']}/share", json={"share": 20})
    # Последний незакреплённый удалить нельзя: закреплённые дают 80%, а не 100%
    r = api.post(f"/api/stream-offers/{o[11111]['id']}/remove")
    assert r.status_code == 422
    s = api.get(f"/api/campaigns/{c['keitaro_id']}").json()["streams"][1]
    assert by_offer(s)[11111]["status"] == "active" and s["share_total"] == 100


def test_cannot_push_empty_stream(api, fake):
    _, c = open_demo(api, fake)
    s = offer_stream(c)
    ids = [o["id"] for o in s["offers"]]
    for i in ids[:-1]:
        api.post(f"/api/stream-offers/{i}/remove")
    s = api.post(f"/api/stream-offers/{ids[-1]}/remove").json()
    assert s["share_total"] == 0
    r = api.post(f"/api/streams/{s['id']}/push")
    assert r.status_code == 422


def test_stats(api, fake):
    cid, c = open_demo(api, fake)
    st = api.get(f"/api/campaigns/{cid}/stats", params={"period": "7d"}).json()
    s = offer_stream(c)
    keys = {f"{s['keitaro_id']}:{o['offer_id']}" for o in s["offers"]}
    assert keys <= st["by_offer"].keys()
    assert st["total"]["clicks"] == sum(v["clicks"] for v in st["by_stream"].values())


def test_no_keitaro_config_gives_503(fake, monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.keitaro import set_keitaro
    from app.main import app

    monkeypatch.setattr("app.keitaro.get_settings", lambda: Settings(_env_file=None, keitaro_url="", keitaro_api_key=""))
    set_keitaro(None)
    try:
        with TestClient(app) as client:
            r = client.get("/api/offers")
        assert r.status_code == 503
        assert "KEITARO_URL" in r.json()["detail"]
    finally:
        set_keitaro(None)


def test_offer_meta_and_filters_summary(api, fake):
    _, c = open_demo(api, fake)
    flow1, flow2 = c["streams"]
    assert flow1["filters_summary"] == "country = AU"
    o = by_offer(flow2)
    assert o[3749]["preview_url"] == "http://kt/lander/miaflow_spin/"
    assert o[11111]["preview_url"].startswith("https://fito.example/")
    assert o[3749]["offer_country"] == "RO"
    assert o[3717]["preview_url"] is None


def test_trends_daily_series(api, fake):
    cid, c = open_demo(api, fake)
    t = api.get(f"/api/campaigns/{cid}/trends", params={"days": 7}).json()
    assert len(t["days"]) == 7 and t["days"] == sorted(t["days"])
    s = offer_stream(c)
    key = f"{s['keitaro_id']}:3749"
    assert len(t["by_offer"][key]["clicks"]) == 7
    assert sum(t["total"]["clicks"]) == sum(sum(v["clicks"]) for v in t["by_stream"].values())
    assert api.get(f"/api/campaigns/{cid}/trends", params={"days": 1}).status_code == 422


def test_imported_campaign_gets_url(api, fake):
    cid, c = open_demo(api, fake)
    assert c["url"] == "https://in.posdk.xyz/wVqN1R"


def test_stream_deleted_in_keitaro(api, fake):
    cid, c = open_demo(api, fake)
    s = offer_stream(c)
    api.post(f"/api/streams/{s['id']}/offers", json={"offer_id": 11112})
    fake.streams[s["keitaro_id"]]["state"] = "deleted"  # удалили в админке
    r = api.post(f"/api/streams/{s['id']}/push")
    assert r.status_code == 422 and "удалён в Keitaro" in r.json()["detail"]
    assert len(fake.streams[s["keitaro_id"]]["offers"]) == 3  # архивный поток не тронут
    c = api.post(f"/api/campaigns/{cid}/fetch").json()
    assert [x["name"] for x in c["streams"]] == ["Flow 1"]
