from backend import discover, locations


def test_catalog_covers_world():
    groups = {g["group"]: g["items"] for g in locations.catalog()}
    assert len(groups["Countries"]) >= 190
    for r in ("APAC", "GCC", "EMEA", "DACH", "LATAM", "Nordics"):
        assert r in groups["Regions"]
    assert "Karnataka" in groups["States & provinces"] and "Bengaluru" in groups["Cities"]
    # every region expands only to real countries
    for countries in locations.REGIONS.values():
        assert set(countries) <= set(locations.COUNTRIES)


def test_clean_and_apollo_expansion():
    assert locations.clean("Any") == [] and locations.clean(["Worldwide", ""]) == []
    assert locations.clean("India, UAE") == ["India", "UAE"]
    out = locations.for_apollo(["GCC", "Bengaluru", "New York State"])
    assert "Saudi Arabia" in out and "Bengaluru" in out and "New York, US" in out
    assert locations.for_apollo(["India", "India"]) == ["India"]


def test_radar_searches_each_place(monkeypatch):
    queries = []
    monkeypatch.setattr(discover.tavily, "raw_search", lambda q, **k: queries.append(q) or [])
    discover.signal_radar("qa_hiring", None, ["India", "GCC", "Germany"], 30)
    assert any(q.endswith(" India") for q in queries) and any(q.endswith(" GCC") for q in queries)
    assert any(q.endswith(" Germany") for q in queries)
    queries.clear()
    discover.signal_radar("qa_hiring", None, [], 30)
    assert queries and not any("India" in q for q in queries)


def test_browse_passes_expanded_locations(monkeypatch):
    seen = {}
    monkeypatch.setattr(discover.apollo, "available", lambda: True)
    monkeypatch.setattr(discover.apollo, "search_companies",
                        lambda **k: seen.update(k) or {"companies": []})
    discover.browse("fintech", ["DACH", "Pune"], None, 1)
    assert seen["locations"] == ["Germany", "Austria", "Switzerland", "Pune"]
