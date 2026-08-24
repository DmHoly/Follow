import json
from pathlib import Path

import pytest

from follow.cli import main

CAKE_STRUCT = {
    "name": "Vanilla cake",
    "ingredients": {"flour": {"value": 200, "unit": "g"}},
    "bake": {"temperature": {"value": 180, "unit": "C"}, "duration": {"value": 35, "unit": "min"}},
}


def _chocolate_cake_struct(entity_id):
    return {
        "name": "Gateau", "trial_id": 0, "entity_id": entity_id,
        "dark_chocolate": {"value": 200, "unit": "g"}, "cocoa_percent": {"value": 64, "unit": "%"},
        "butter": {"value": 150, "unit": "g"}, "sugar": {"value": 180, "unit": "g"}, "eggs": 4,
        "flour": {"value": 120, "unit": "g"}, "baking_powder": {"value": 5, "unit": "g"},
        "bake_temperature": {"value": 180, "unit": "C"}, "bake_duration": {"value": 35, "unit": "min"},
    }


def _write_json(path: Path, data) -> str:
    path.write_text(json.dumps(data))
    return str(path)


def test_init_rejects_a_non_empty_directory(tmp_path, capsys):
    (tmp_path / "something").write_text("x")
    assert main(["init", str(tmp_path)]) == 1
    assert "erreur" in capsys.readouterr().err


def test_full_git_like_workflow(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)

    assert main(["init", repo_path]) == 0
    capsys.readouterr()

    draft_path = str(tmp_path / "draft.json")
    assert (
        main(
            [
                "new",
                "--repo",
                repo_path,
                "--branch",
                "main",
                "--title",
                "Baseline",
                "--intent",
                "Reference bake",
                "--structure-type",
                "examples.recipe.CakeRecipe",
                "--structure-file",
                struct_file,
                "--out",
                draft_path,
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["commit", draft_path, "--repo", repo_path]) == 0
    baseline_id = capsys.readouterr().out.split()[0]
    assert baseline_id.startswith("exp_")

    assert main(["log", "main", "--repo", repo_path]) == 0
    assert baseline_id in capsys.readouterr().out

    derive_draft = str(tmp_path / "derive_draft.json")
    assert (
        main(
            [
                "derive",
                baseline_id,
                "--repo",
                repo_path,
                "--title",
                "More flour",
                "--intent",
                "Does more flour help?",
                "--out",
                derive_draft,
            ]
        )
        == 0
    )
    capsys.readouterr()

    payload = json.loads(Path(derive_draft).read_text())
    assert payload["references"][0]["role"] == "baseline"
    assert payload["references"][0]["experiment_id"] == baseline_id
    payload["structure"]["ingredients"]["flour"]["value"] = 240
    payload["conclusion"] = {"status": "concluded", "decision": "promote", "summary": "Better rise."}
    Path(derive_draft).write_text(json.dumps(payload))

    assert main(["commit", derive_draft, "--repo", repo_path]) == 0
    variant_id = capsys.readouterr().out.split()[0]

    assert main(["show", variant_id, "--repo", repo_path]) == 0
    fiche = capsys.readouterr().out
    assert "promote" in fiche
    assert "ingredients.flour" in fiche

    assert main(["diff", baseline_id, variant_id, "--repo", repo_path]) == 0
    assert "ingredients.flour" in capsys.readouterr().out

    assert main(["branch", "--repo", repo_path]) == 0
    assert "main" in capsys.readouterr().out

    assert main(["tag", "champion", "--at", variant_id, "--repo", repo_path]) == 0
    capsys.readouterr()
    assert main(["show", "champion", "--repo", repo_path]) == 0
    assert variant_id in capsys.readouterr().out

    graph_out = str(tmp_path / "graph.html")
    assert main(["graph", "--repo", repo_path, "--out", graph_out]) == 0
    assert Path(graph_out).exists()

    # a fresh Repository reload sees everything a second CLI process would
    from follow import Repository

    reloaded = Repository(repo_path)
    assert len(reloaded) == 2
    assert reloaded.tags["champion"] == variant_id


def test_branch_without_at_fails_clearly(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()
    assert main(["branch", "unknown-branch", "--repo", repo_path]) == 1
    assert "--at" in capsys.readouterr().err


def test_merge_via_cli_selects_a_single_step_from_the_test_branch(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()

    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)
    draft = str(tmp_path / "v1.json")
    main(
        [
            "new",
            "--repo",
            repo_path,
            "--branch",
            "main",
            "--title",
            "Baseline",
            "--intent",
            "start",
            "--structure-type",
            "examples.recipe.CakeRecipe",
            "--structure-file",
            struct_file,
            "--out",
            draft,
        ]
    )
    capsys.readouterr()
    payload = json.loads(Path(draft).read_text())
    payload["steps"] = [
        {"order": 1, "name": "Mix"},
        {"order": 2, "name": "Rest"},
        {"order": 3, "name": "Bake", "parameters": {"temperature": {"value": 170, "unit": "C"}}},
        {"order": 4, "name": "Cool"},
        {"order": 5, "name": "Ice"},
    ]
    Path(draft).write_text(json.dumps(payload))
    assert main(["commit", draft, "--repo", repo_path]) == 0
    v1_id = capsys.readouterr().out.split()[0]

    branch_draft = str(tmp_path / "branch.json")
    assert (
        main(
            [
                "derive",
                v1_id,
                "--repo",
                repo_path,
                "--new-branch",
                "essai-cuisson",
                "--title",
                "Essai 185C",
                "--intent",
                "Tester une cuisson plus vive",
                "--out",
                branch_draft,
            ]
        )
        == 0
    )
    capsys.readouterr()
    payload = json.loads(Path(branch_draft).read_text())
    payload["steps"][2]["parameters"]["temperature"]["value"] = 185
    payload["conclusion"] = {"status": "concluded", "decision": "promote", "summary": "Meilleure levée."}
    Path(branch_draft).write_text(json.dumps(payload))
    assert main(["commit", branch_draft, "--repo", repo_path]) == 0
    branch_tip_id = capsys.readouterr().out.split()[0]

    assert main(["diff", v1_id, branch_tip_id, "--repo", repo_path, "--steps"]) == 0
    diff_out = capsys.readouterr().out
    assert "[2].parameters.temperature" in diff_out

    merge_draft = str(tmp_path / "merge.json")
    assert (
        main(
            [
                "merge",
                "main",
                branch_tip_id,
                "--repo",
                repo_path,
                "--title",
                "Fusion cuisson",
                "--intent",
                "Adopter uniquement la cuisson optimisée",
                "--take-steps",
                "[2]",
                "--out",
                merge_draft,
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["commit", merge_draft, "--repo", repo_path]) == 0
    merge_id = capsys.readouterr().out.split()[0]

    from follow import Repository

    repo = Repository(repo_path)
    merged = repo.get(merge_id)
    assert set(merged.parents) == {v1_id, branch_tip_id}
    assert merged.steps[2].parameters["temperature"].value == 185
    assert merged.steps[0].name == "Mix"
    assert repo.branches["main"] == merge_id


def test_cli_reports_a_clean_error_instead_of_a_traceback_on_tag_repoint(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()

    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)
    draft = str(tmp_path / "v1.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", "main", "--title", "v1", "--intent", "start",
            "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", struct_file, "--out", draft,
        ]
    )
    capsys.readouterr()
    main(["commit", draft, "--repo", repo_path])
    v1_id = capsys.readouterr().out.split()[0]

    assert main(["tag", "release", "--at", v1_id, "--repo", repo_path]) == 0
    capsys.readouterr()

    derive_draft = str(tmp_path / "v2.json")
    main(["derive", v1_id, "--repo", repo_path, "--title", "v2", "--intent", "x", "--out", derive_draft])
    capsys.readouterr()
    main(["commit", derive_draft, "--repo", repo_path])
    v2_id = capsys.readouterr().out.split()[0]

    # repointing without --force is a clean, single-line CLI error, not a traceback
    assert main(["tag", "release", "--at", v2_id, "--repo", repo_path]) == 1
    err = capsys.readouterr().err
    assert err.startswith("erreur:")
    assert "immutable" in err
    assert "Traceback" not in err

    # --force is the documented escape hatch
    assert main(["tag", "release", "--at", v2_id, "--repo", repo_path, "--force"]) == 0


def test_cli_reports_a_clean_error_on_branch_tag_namespace_collision(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()

    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)
    draft = str(tmp_path / "v1.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", "main", "--title", "v1", "--intent", "start",
            "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", struct_file, "--out", draft,
        ]
    )
    capsys.readouterr()
    main(["commit", draft, "--repo", repo_path])
    v1_id = capsys.readouterr().out.split()[0]

    main(["tag", "same-name", "--at", v1_id, "--repo", repo_path])
    capsys.readouterr()

    assert main(["branch", "same-name", "--at", v1_id, "--repo", repo_path]) == 1
    err = capsys.readouterr().err
    assert err.startswith("erreur:")
    assert "namespace" in err
    assert "Traceback" not in err


def test_new_refuses_to_clobber_an_existing_draft_without_force(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()

    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)
    draft = str(tmp_path / "draft.json")
    args = [
        "new", "--repo", repo_path, "--branch", "main", "--title", "v1", "--intent", "start",
        "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", struct_file, "--out", draft,
    ]
    assert main(args) == 0
    capsys.readouterr()

    # hand-edit the draft - this must survive a re-run without --force
    payload = json.loads(Path(draft).read_text())
    payload["intent"] = "precious hand edit"
    Path(draft).write_text(json.dumps(payload))

    assert main(args) == 1
    err = capsys.readouterr().err
    assert "existe déjà" in err
    assert json.loads(Path(draft).read_text())["intent"] == "precious hand edit"  # untouched

    assert main(args + ["--force"]) == 0
    assert json.loads(Path(draft).read_text())["intent"] == "start"  # now overwritten, deliberately


def test_committing_the_same_unmodified_draft_twice_is_refused_like_git(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()

    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)
    draft = str(tmp_path / "draft.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", "main", "--title", "v1", "--intent", "start",
            "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", struct_file, "--out", draft,
        ]
    )
    capsys.readouterr()

    assert main(["commit", draft, "--repo", repo_path]) == 0
    first_id = capsys.readouterr().out.split()[0]

    # re-running commit on the exact same, unmodified file (e.g. a retried script) is refused,
    # like `git commit` with nothing staged - not a silent duplicate, not a silent no-op
    assert main(["commit", draft, "--repo", repo_path]) == 1
    err = capsys.readouterr().err
    assert "nothing to commit" in err
    assert first_id in err

    from follow import Repository

    repo = Repository(repo_path)
    assert len(repo) == 1


def test_malformed_structure_json_is_a_clean_message_not_a_traceback(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{not valid json")

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "new", "--repo", str(tmp_path / "repo"), "--branch", "main", "--title", "v1", "--intent", "x",
                "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", str(bad),
            ]
        )
    assert "JSON valide" in str(excinfo.value)


def test_missing_structure_file_is_a_clean_message_not_a_traceback(tmp_path):
    missing = tmp_path / "does_not_exist.json"

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "new", "--repo", str(tmp_path / "repo"), "--branch", "main", "--title", "v1", "--intent", "x",
                "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", str(missing),
            ]
        )
    assert "introuvable" in str(excinfo.value)


def test_structure_file_pointing_at_a_directory_is_a_clean_message(tmp_path):
    a_directory = tmp_path / "oops_a_dir"
    a_directory.mkdir()

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "new", "--repo", str(tmp_path / "repo"), "--branch", "main", "--title", "v1", "--intent", "x",
                "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", str(a_directory),
            ]
        )
    assert "dossier" in str(excinfo.value)


def test_malformed_draft_json_on_commit_is_a_clean_message(tmp_path):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    bad_draft = tmp_path / "bad_draft.json"
    bad_draft.write_text("{not valid")

    with pytest.raises(SystemExit) as excinfo:
        main(["commit", str(bad_draft), "--repo", repo_path])
    assert "JSON valide" in str(excinfo.value)


def test_init_on_a_path_that_is_a_file_fails_cleanly(tmp_path, capsys):
    not_a_dir = tmp_path / "somefile.txt"
    not_a_dir.write_text("x")

    assert main(["init", str(not_a_dir)]) == 1
    err = capsys.readouterr().err
    assert "n'est pas un dossier" in err
    assert "Traceback" not in err


def test_log_with_a_negative_number_fails_clearly_instead_of_silently_slicing(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()

    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)
    draft = str(tmp_path / "draft.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", "main", "--title", "v1", "--intent", "start",
            "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", struct_file, "--out", draft,
        ]
    )
    capsys.readouterr()
    main(["commit", draft, "--repo", repo_path])
    capsys.readouterr()

    assert main(["log", "main", "--repo", repo_path, "-n", "-1"]) == 1
    err = capsys.readouterr().err
    assert "positif" in err


WAFER_LOT_STRUCT = {
    "lot_id": "LOT-A",
    "wafer_diameter": {"value": 200, "unit": "mm"},
    "process": "implant+anneal",
    "wafers": [
        {"slot": 1, "implant_dose": {"value": 2, "unit": "1e14 cm^-2"}, "anneal_temperature": {"value": 900, "unit": "C"}, "anneal_duration": {"value": 30, "unit": "min"}},
        {"slot": 2, "implant_dose": {"value": 4, "unit": "1e14 cm^-2"}, "anneal_temperature": {"value": 900, "unit": "C"}, "anneal_duration": {"value": 30, "unit": "min"}},
        {"slot": 3, "implant_dose": {"value": 6, "unit": "1e14 cm^-2"}, "anneal_temperature": {"value": 900, "unit": "C"}, "anneal_duration": {"value": 30, "unit": "min"}},
    ],
}


def _commit_wafer_lot(tmp_path, repo_path, capsys) -> str:
    main(["init", repo_path])
    capsys.readouterr()
    struct_file = _write_json(tmp_path / "lot.json", WAFER_LOT_STRUCT)
    draft = str(tmp_path / "draft.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", "main", "--title", "LOT-A", "--intent", "split factoriel",
            "--structure-type", "examples.wafer_doe.WaferLot", "--structure-file", struct_file, "--out", draft,
        ]
    )
    capsys.readouterr()
    main(["commit", draft, "--repo", repo_path])
    return capsys.readouterr().out.split()[0]


def test_explode_prints_constant_and_varying_parameters(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    _commit_wafer_lot(tmp_path, repo_path, capsys)

    assert main(["explode", "main", "wafers", "--repo", repo_path, "--ignore", "slot"]) == 0
    out = capsys.readouterr().out
    assert "3 entités" in out
    assert "anneal_temperature: 900 C" in out  # constant across all 3
    assert "implant_dose: [2 1e14 cm^-2, 4 1e14 cm^-2, 6 1e14 cm^-2]" in out  # varying


def test_explode_writes_an_html_page_with_out(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    _commit_wafer_lot(tmp_path, repo_path, capsys)

    out_file = str(tmp_path / "explode.html")
    assert main(["explode", "main", "wafers", "--repo", repo_path, "--out", out_file]) == 0
    html = Path(out_file).read_text()
    assert "implant_dose" in html
    assert "<style>" in html


def test_explode_on_a_non_list_field_fails_clearly(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    _commit_wafer_lot(tmp_path, repo_path, capsys)

    assert main(["explode", "main", "lot_id", "--repo", repo_path]) == 1
    err = capsys.readouterr().err
    assert "n'est pas une liste" in err


def test_explode_on_an_unknown_field_fails_clearly(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    _commit_wafer_lot(tmp_path, repo_path, capsys)

    assert main(["explode", "main", "does_not_exist", "--repo", repo_path]) == 1
    err = capsys.readouterr().err
    assert "does_not_exist" in err


def test_new_prints_a_hint_when_the_repository_has_a_commit_form(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()
    Path(repo_path, "commit_form.yml").write_text(
        "title: Formulaire de commit\nfields:\n  - name: operator\n    label: Opérateur\n    type: string\n    required: true\n"
    )

    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)
    draft = str(tmp_path / "draft.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", "main", "--title", "v1", "--intent", "start",
            "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", struct_file, "--out", draft,
        ]
    )
    out = capsys.readouterr().out
    assert "Formulaire de commit" in out
    assert "operator" in out

    # committing without filling form_answers is refused with every problem listed
    assert main(["commit", draft, "--repo", repo_path]) == 1
    err = capsys.readouterr().err
    assert "operator" in err

    payload = json.loads(Path(draft).read_text())
    payload["form_answers"] = {"operator": "Alice"}
    Path(draft).write_text(json.dumps(payload))
    assert main(["commit", draft, "--repo", repo_path]) == 0


def _commit_chocolate_cake(tmp_path, repo_path, capsys, *, branch, title, entity_id):
    struct_file = _write_json(tmp_path / f"{branch}-cake.json", _chocolate_cake_struct(entity_id))
    draft = str(tmp_path / f"{branch}-draft.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", branch, "--title", title, "--intent", "start",
            "--structure-type", "examples.chocolate_cake.ChocolateCake", "--structure-file", struct_file, "--out", draft,
        ]
    )
    capsys.readouterr()
    main(["commit", draft, "--repo", repo_path])
    return capsys.readouterr().out.split()[0]


def test_trace_reports_no_match_for_an_unmentioned_entity(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()
    _commit_chocolate_cake(tmp_path, repo_path, capsys, branch="main", title="v1", entity_id="moule-vert")

    assert main(["trace", "inexistant", "--repo", repo_path]) == 0
    out = capsys.readouterr().out
    assert "aucune expérience" in out
    assert "inexistant" in out


def test_trace_links_two_unrelated_experiments_by_shared_entity_id(tmp_path, capsys):
    # the physical-entity scenario: two branches, no parent/derive relationship between them,
    # just the same entity_id string reused - `trace` must find both anyway.
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()
    batch_id = _commit_chocolate_cake(tmp_path, repo_path, capsys, branch="main", title="Split moules", entity_id="moule-vert")
    followup_id = _commit_chocolate_cake(tmp_path, repo_path, capsys, branch="moule-vert-nutella", title="Injection Nutella", entity_id="moule-vert")

    assert main(["trace", "moule-vert", "--repo", repo_path]) == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 2
    assert batch_id in lines[0] and "Split moules" in lines[0]
    assert followup_id in lines[1] and "Injection Nutella" in lines[1]


def test_explode_html_escapes_an_experiment_title_containing_markup(tmp_path, capsys):
    # the experiment's title is repository data, and `explode --out` feeds it to render_page's
    # raw-HTML heading slot - it must arrive escaped, not as live markup
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()
    struct = dict(WAFER_LOT_STRUCT)
    struct_file = _write_json(tmp_path / "lot.json", struct)
    draft = str(tmp_path / "draft.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", "main",
            "--title", "Lot <img src=x onerror=alert(1)>", "--intent", "split",
            "--structure-type", "examples.wafer_doe.WaferLot", "--structure-file", struct_file,
            "--out", draft,
        ]
    )
    capsys.readouterr()
    main(["commit", draft, "--repo", repo_path])
    capsys.readouterr()

    out_file = tmp_path / "explode.html"
    assert main(["explode", "main", "wafers", "--repo", repo_path, "--out", str(out_file)]) == 0
    html = out_file.read_text()
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_report_html_escapes_a_title_passed_on_the_command_line(tmp_path, capsys):
    repo_path = str(tmp_path / "repo")
    main(["init", repo_path])
    capsys.readouterr()
    struct_file = _write_json(tmp_path / "cake.json", CAKE_STRUCT)
    draft = str(tmp_path / "draft.json")
    main(
        [
            "new", "--repo", repo_path, "--branch", "main", "--title", "v1", "--intent", "start",
            "--structure-type", "examples.recipe.CakeRecipe", "--structure-file", struct_file, "--out", draft,
        ]
    )
    capsys.readouterr()
    main(["commit", draft, "--repo", repo_path])
    capsys.readouterr()

    out_file = tmp_path / "report.html"
    assert main(["report", "--repo", repo_path, "--title", "<script>alert(1)</script>",
                 "--out", str(out_file), "--no-embed"]) == 0
    assert "<script>alert(1)</script>" not in out_file.read_text()
