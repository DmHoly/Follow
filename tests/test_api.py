"""Functional tests for follow.api: the FastAPI surface over Repository (follow.api.app),
plus follow.api.server's start/stop process management.
"""

import time

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient

from follow.api.app import create_app  # noqa: E402

CAKE_STRUCT = {
    "name": "Vanilla cake",
    "ingredients": {"flour": {"value": 200, "unit": "g"}},
    "bake": {"temperature": {"value": 180, "unit": "C"}, "duration": {"value": 35, "unit": "min"}},
}
STRUCTURE_TYPE = "examples.recipe.CakeRecipe"


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "repo", structure_modules=[STRUCTURE_TYPE.rsplit(".", 1)[0]])
    return TestClient(app)


def _new_payload(**overrides):
    payload = {
        "branch": "main",
        "structure_type": STRUCTURE_TYPE,
        "structure": CAKE_STRUCT,
        "title": "Essai 1",
        "intent": "voir si ça marche",
    }
    payload.update(overrides)
    return payload


def test_health_reports_repo_and_no_failed_imports(client, tmp_path):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["experiments"] == 0
    assert body["running"] == 0
    assert body["completed"] == 0
    assert body["branches"] == 0
    assert body["failed_structure_imports"] == []


def test_health_counts_running_and_completed_experiments(client):
    client.post("/api/experiments", json=_new_payload())  # default conclusion.status == "draft"
    resp = client.get("/api/health")
    body = resp.json()
    assert body["experiments"] == 1
    assert body["running"] == 1
    assert body["completed"] == 0
    assert body["branches"] == 1


def test_structures_lists_registered_types_with_json_schema(client):
    resp = client.get("/api/structures")
    assert resp.status_code == 200
    keys = {row["key"] for row in resp.json()}
    assert STRUCTURE_TYPE in keys

    resp = client.get(f"/api/structures/{STRUCTURE_TYPE}/schema")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["properties"]["name"]["type"] == "string"
    assert "$defs" in schema  # BakeStep/Quantity nested models


def test_unknown_structure_schema_is_404(client):
    resp = client.get("/api/structures/not.a.real.Type/schema")
    assert resp.status_code == 404


def test_new_experiment_commits_and_is_readable(client):
    resp = client.post("/api/experiments", json=_new_payload())
    assert resp.status_code == 201, resp.text
    exp = resp.json()["experiment"]
    assert exp["title"] == "Essai 1"
    assert exp["branch"] == "main"
    assert exp["parents"] == []

    resp = client.get("/api/branches")
    assert resp.json() == {"main": exp["id"]}

    resp = client.get(f"/api/experiments/{exp['id']}")
    assert resp.status_code == 200
    assert resp.json()["experiment"]["id"] == exp["id"]
    assert "# Essai 1" in resp.json()["fiche_markdown"]

    resp = client.get("/api/log/main")
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["offset"] == 0


def test_new_experiment_with_bad_structure_type_is_400(client):
    resp = client.post("/api/experiments", json=_new_payload(structure_type="nope.Nope"))
    assert resp.status_code == 400


def test_new_experiment_with_invalid_structure_body_is_422(client):
    bad = dict(CAKE_STRUCT)
    del bad["name"]  # required field missing
    resp = client.post("/api/experiments", json=_new_payload(structure=bad))
    assert resp.status_code == 422


def test_derive_carries_structure_and_adds_baseline_reference(client):
    parent = client.post("/api/experiments", json=_new_payload()).json()["experiment"]

    resp = client.post(
        f"/api/experiments/{parent['id']}/derive",
        json={"title": "Essai 2", "intent": "un peu plus de sucre"},
    )
    assert resp.status_code == 201, resp.text
    child = resp.json()["experiment"]
    assert child["parents"] == [parent["id"]]
    assert child["branch"] == "main"
    baseline = next(r for r in child["references"] if r["role"] == "baseline")
    assert baseline["experiment_id"] == parent["id"]


def test_log_pagination(client):
    parent = client.post("/api/experiments", json=_new_payload()).json()["experiment"]
    ref = parent["id"]
    for i in range(4):
        ref = client.post(
            f"/api/experiments/{ref}/derive",
            json={"title": f"Essai {i + 2}", "intent": "suite"},
        ).json()["experiment"]["id"]
    # 5 commits total on main now

    resp = client.get("/api/log/main?limit=2")
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["items"][0]["title"] == "Essai 5"  # newest first

    resp = client.get("/api/log/main?offset=2&limit=2")
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["items"][0]["title"] == "Essai 3"

    resp = client.get("/api/log/main?offset=4&limit=2")
    assert len(resp.json()["items"]) == 1  # last page, shorter than limit

    resp = client.get("/api/log/main?offset=100&limit=2")
    assert resp.json()["items"] == []

    assert client.get("/api/log/main?offset=-1").status_code == 422
    assert client.get("/api/log/main?limit=0").status_code == 422
    assert client.get("/api/log/main?limit=501").status_code == 422


def test_derive_can_conclude_with_evidence_and_objective_results(client):
    parent = client.post(
        "/api/experiments",
        json=_new_payload(objectives=[{"name": "rise", "metric": "height_cm", "direction": "maximize", "target": 5}]),
    ).json()["experiment"]

    resp = client.post(
        f"/api/experiments/{parent['id']}/derive",
        json={
            "title": "Essai 1 - conclu",
            "intent": "conclure sur l'essai précédent",
            "structure": None,
            "carry_objectives": True,
            "evidence": [{"id": "photo-1", "description": "photo du gâteau", "source": "photo-1.jpg"}],
            "conclusion": {
                "status": "concluded",
                "decision": "promote",
                "summary": "le gâteau a bien levé",
                "objective_results": [{"objective": "rise", "status": "met", "reasoning": "mesuré à 6cm"}],
            },
        },
    )
    assert resp.status_code == 201, resp.text
    child = resp.json()["experiment"]
    assert child["conclusion"]["status"] == "concluded"
    assert child["conclusion"]["objective_results"][0]["objective"] == "rise"
    assert child["evidence"][0]["id"] == "photo-1"


def test_derive_unknown_ref_is_404(client):
    resp = client.post(
        "/api/experiments/does-not-exist/derive",
        json={"title": "x", "intent": "y"},
    )
    assert resp.status_code == 404


def test_diff_between_two_experiments(client):
    parent = client.post("/api/experiments", json=_new_payload()).json()["experiment"]
    changed_structure = {**CAKE_STRUCT, "name": "Chocolate cake"}
    child = client.post(
        f"/api/experiments/{parent['id']}/derive",
        json={"title": "Essai 2", "intent": "renommé", "structure": changed_structure},
    ).json()["experiment"]

    resp = client.get(f"/api/diff?a={parent['id']}&b={child['id']}")
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert any(e["path"] == "name" and e["kind"] == "changed" for e in entries)


def test_branch_and_tag_endpoints(client):
    exp = client.post("/api/experiments", json=_new_payload()).json()["experiment"]

    resp = client.post("/api/branches", json={"name": "feature", "at": exp["id"]})
    assert resp.status_code == 200
    assert resp.json()["feature"] == exp["id"]

    resp = client.post("/api/tags", json={"name": "v1", "at": exp["id"]})
    assert resp.status_code == 200
    assert resp.json()["v1"] == exp["id"]

    # tags are immutable without force=True
    other = client.post("/api/experiments", json=_new_payload(title="Essai 2")).json()["experiment"]
    resp = client.post("/api/tags", json={"name": "v1", "at": other["id"]})
    assert resp.status_code == 400


def test_merge_two_branches(client):
    root = client.post("/api/experiments", json=_new_payload()).json()["experiment"]
    a = client.post(
        f"/api/experiments/{root['id']}/derive",
        json={"title": "branche A", "intent": "a", "new_branch": "a"},
    ).json()["experiment"]
    b = client.post(
        f"/api/experiments/{root['id']}/derive",
        json={"title": "branche B", "intent": "b", "new_branch": "b"},
    ).json()["experiment"]

    resp = client.post(
        "/api/merge",
        json={"ref_a": a["id"], "ref_b": b["id"], "title": "fusion", "intent": "réunir a et b"},
    )
    assert resp.status_code == 201, resp.text
    merged = resp.json()["experiment"]
    assert sorted(merged["parents"]) == sorted([a["id"], b["id"]])


def test_merge_same_commit_is_409(client):
    exp = client.post("/api/experiments", json=_new_payload()).json()["experiment"]
    resp = client.post(
        "/api/merge",
        json={"ref_a": exp["id"], "ref_b": exp["id"], "title": "x", "intent": "y"},
    )
    assert resp.status_code == 409


def test_nothing_to_commit_is_409(client):
    # explicit parents=[] on both calls so the second is content-identical to the first
    # (including parents) - the same "nothing changed since the tip" case `git commit` refuses.
    client.post("/api/experiments", json=_new_payload(parents=[]))
    resp = client.post("/api/experiments", json=_new_payload(parents=[]))
    assert resp.status_code == 409


def test_get_missing_experiment_is_404_with_plain_message(client):
    resp = client.get("/api/experiments/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No experiment, branch or tag matches 'does-not-exist'"


def test_list_experiments_filters_by_status_across_branches(client):
    running = client.post("/api/experiments", json=_new_payload(branch="main")).json()["experiment"]
    other_branch = client.post(
        "/api/experiments",
        json=_new_payload(branch="side", title="Essai 2"),
    ).json()["experiment"]
    completed = client.post(
        f"/api/experiments/{other_branch['id']}/derive",
        json={
            "title": "Essai 2 - conclu",
            "intent": "conclure",
            "conclusion": {"status": "concluded", "summary": "ok"},
        },
    ).json()["experiment"]

    resp = client.get("/api/experiments?status=running")
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    # both draft commits are "running": main's tip, and side's now-superseded first commit -
    # /api/experiments lists every experiment in the repo, not just branch tips.
    assert ids == {running["id"], other_branch["id"]}
    assert body["total"] == 2

    resp = client.get("/api/experiments?status=completed")
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    assert ids == {completed["id"]}

    resp = client.get("/api/experiments?status=all")
    assert resp.json()["total"] == 3  # running + the draft other_branch tip + completed

    assert client.get("/api/experiments?status=bogus").status_code == 422


def test_list_experiments_pagination_and_ordering(client):
    for i in range(3):
        client.post("/api/experiments", json=_new_payload(branch=f"b{i}", title=f"Essai {i}"))
    resp = client.get("/api/experiments?limit=2")
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["items"][0]["title"] == "Essai 2"  # newest first


def test_examples_endpoint_lists_only_existing_files(client):
    resp = client.get("/api/examples")
    assert resp.status_code == 200
    for entry in resp.json():
        assert "title" in entry and "description" in entry and "file" in entry


def test_app_shell_served_for_deep_links(client):
    for path in ("/app", "/app/en-cours", "/app/experience/some-id", "/app/graphe"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "text/html" in resp.headers["content-type"]
        assert 'id="view"' in resp.text


def test_docs_route_exists(client):
    resp = client.get("/docs")
    # either the built Sphinx site (redirect to index) or the friendly "not built" fallback
    assert resp.status_code in (200, 307, 404)


def test_graph_html_endpoint(client):
    resp = client.get("/api/graph.html")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "vide" in resp.text  # empty repo -> placeholder message

    client.post("/api/experiments", json=_new_payload())
    resp = client.get("/api/graph.html")
    assert resp.status_code == 200
    assert "plotly" in resp.text.lower()


def test_index_page_and_static_assets_are_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]

    resp = client.get("/static/app.js")
    assert resp.status_code == 200


def test_commit_form_endpoint_reports_none_when_unconfigured(client):
    resp = client.get("/api/commit_form")
    assert resp.status_code == 200
    assert resp.json() is None


def test_entities_trace_endpoint(client, tmp_path):
    structure = {**CAKE_STRUCT}
    client.post("/api/experiments", json=_new_payload(structure=structure))
    resp = client.get("/api/entities/moule-1")
    assert resp.status_code == 200
    assert resp.json() == []


# -- process management (follow.api.server) --------------------------------------------------


def test_server_start_stop_status_lifecycle(tmp_path, monkeypatch):
    server = pytest.importorskip("follow.api.server")
    monkeypatch.setattr(server, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(server, "PID_FILE", tmp_path / "state" / "server.pid")
    monkeypatch.setattr(server, "META_FILE", tmp_path / "state" / "server.json")
    monkeypatch.setattr(server, "LOG_FILE", tmp_path / "state" / "server.log")

    assert server.status() is None
    assert server.stop() is False

    repo_path = tmp_path / "repo"
    meta = server.start(repo_path, port=8931, startup_timeout=15)
    try:
        assert meta["repo"] == str(repo_path.resolve())
        assert server.status() is not None

        with pytest.raises(server.ServerError):
            server.start(repo_path, port=8932)
    finally:
        assert server.stop() is True

    assert server.status() is None
    # a second stop is a no-op, not an error
    assert server.stop() is False


def test_server_start_that_never_becomes_healthy_leaves_no_state(tmp_path, monkeypatch):
    server = pytest.importorskip("follow.api.server")
    monkeypatch.setattr(server, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(server, "PID_FILE", tmp_path / "state" / "server.pid")
    monkeypatch.setattr(server, "META_FILE", tmp_path / "state" / "server.json")
    monkeypatch.setattr(server, "LOG_FILE", tmp_path / "state" / "server.log")

    # A timeout far too short for uvicorn to ever come up simulates a server that fails to
    # start (bad config, port taken, broken structure import...): start() must raise rather
    # than report success, and must not leave a pidfile pointing at a since-killed process.
    with pytest.raises(server.ServerError):
        server.start(tmp_path / "repo", port=8933, startup_timeout=0.01)
    assert server.status() is None


# -- follow_api CLI (argument parsing / wiring to follow.api.server) -------------------------


def test_cli_status_reports_nothing_running(tmp_path, monkeypatch, capsys):
    cli = pytest.importorskip("follow.api.cli")
    server = pytest.importorskip("follow.api.server")
    monkeypatch.setattr(server, "PID_FILE", tmp_path / "server.pid")
    monkeypatch.setattr(server, "META_FILE", tmp_path / "server.json")

    assert cli.main(["status"]) == 1
    assert "Aucun serveur" in capsys.readouterr().out


def test_cli_stop_when_nothing_running_is_not_an_error(tmp_path, monkeypatch, capsys):
    cli = pytest.importorskip("follow.api.cli")
    server = pytest.importorskip("follow.api.server")
    monkeypatch.setattr(server, "PID_FILE", tmp_path / "server.pid")
    monkeypatch.setattr(server, "META_FILE", tmp_path / "server.json")

    assert cli.main(["stop"]) == 0
    assert "Aucun serveur" in capsys.readouterr().out


def test_cli_start_stop_lifecycle(tmp_path, monkeypatch, capsys):
    cli = pytest.importorskip("follow.api.cli")
    server = pytest.importorskip("follow.api.server")
    monkeypatch.setattr(server, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(server, "PID_FILE", tmp_path / "state" / "server.pid")
    monkeypatch.setattr(server, "META_FILE", tmp_path / "state" / "server.json")
    monkeypatch.setattr(server, "LOG_FILE", tmp_path / "state" / "server.log")

    repo = tmp_path / "repo"
    rc = cli.main(["start", "--repo", str(repo), "--port", "8934", "--timeout", "15"])
    try:
        assert rc == 0
        assert "démarrée" in capsys.readouterr().out
        assert cli.main(["status"]) == 0
    finally:
        assert cli.main(["stop"]) == 0
    assert cli.main(["status"]) == 1


def test_cli_logs_prints_log_path(capsys):
    cli = pytest.importorskip("follow.api.cli")
    server = pytest.importorskip("follow.api.server")
    assert cli.main(["logs"]) == 0
    assert str(server.LOG_FILE) in capsys.readouterr().out
