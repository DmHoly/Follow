import json
from pathlib import Path

from follow.cli import main

CAKE_STRUCT = {
    "name": "Vanilla cake",
    "ingredients": {"flour": {"value": 200, "unit": "g"}},
    "bake": {"temperature": {"value": 180, "unit": "C"}, "duration": {"value": 35, "unit": "min"}},
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


def test_committing_the_same_unmodified_draft_twice_is_a_no_op_not_a_duplicate(tmp_path, capsys):
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

    # re-running commit on the exact same, unmodified file (e.g. a retried script) must not
    # create a second, orphaned commit
    assert main(["commit", draft, "--repo", repo_path]) == 0
    second_id = capsys.readouterr().out.split()[0]
    assert second_id == first_id

    from follow import Repository

    repo = Repository(repo_path)
    assert len(repo) == 1
