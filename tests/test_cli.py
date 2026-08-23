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
