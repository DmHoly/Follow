"""Several unrelated domains ("themes") committed to the *same* repository, interleaved as if
several people were working in parallel (recipe work, then a MOSFET commit, then back to the
recipe, etc.) rather than one domain finishing before the next starts. This is the scenario the
"git engine" (Repository/Structure registry/diffing/graphing/report) must handle correctly:
nothing about it assumes a single domain per repo, so nothing should leak or collide between
branches that happen to hold completely different Structure subclasses.
"""

from __future__ import annotations

from examples.chocolate_fondant import Mold, MoltenChocolateCake
from examples.mosfet import Layer, MOSFETStructure
from examples.recipe import BakeStep, CakeRecipe
from examples.solar_cell import PNJunction, SolarCell, SolarModule
from follow import Quantity, Repository, Structure, diff_structures, render_study_html
from follow.graphing import build_graph_figure


def _recipe(flour_g: float) -> CakeRecipe:
    return CakeRecipe(
        name="Gateau",
        ingredients={"farine": Quantity(value=flour_g, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def _mosfet(gate_length_nm: float) -> MOSFETStructure:
    return MOSFETStructure(
        gate_length=Quantity(value=gate_length_nm, unit="nm"),
        gate_oxide=Layer(material="HfO2", thickness=Quantity(value=2, unit="nm")),
        channel_doping=Quantity(value=1e17, unit="cm^-3"),
        source=Layer(material="Si:P", thickness=Quantity(value=50, unit="nm")),
        drain=Layer(material="Si:P", thickness=Quantity(value=50, unit="nm")),
    )


def _solar_module(depletion_width_um: float) -> SolarModule:
    return SolarModule(
        cells=[
            SolarCell(
                junction=PNJunction(
                    n_layer=Layer(material="Si:P", thickness=Quantity(value=200, unit="nm")),
                    p_layer=Layer(material="Si:B", thickness=Quantity(value=180, unit="um")),
                    depletion_width=Quantity(value=depletion_width_um, unit="um"),
                ),
            )
        ],
        encapsulant="EVA",
        frame_material="aluminium",
    )


def _fondant(chocolate_g: float) -> MoltenChocolateCake:
    return MoltenChocolateCake(
        servings=4,
        dark_chocolate=Quantity(value=chocolate_g, unit="g"),
        dark_chocolate_cacao_percent=Quantity(value=64, unit="%"),
        butter=Quantity(value=125, unit="g"),
        sugar=Quantity(value=90, unit="g"),
        whole_eggs=4,
        egg_yolks=0,
        flour=Quantity(value=50, unit="g"),
        mold=Mold(kind="ramequins", count=4),
    )


def _build_multi_domain_repo() -> Repository:
    """Four unrelated experiment lines, committed interleaved rather than one after another -
    baseline for domain A, baseline for B, variant for A, baseline for C, variant for B, ...
    """
    repo = Repository()

    recipe_v1 = repo.new(branch="recipe", structure=_recipe(200), title="Recette de base", intent="reference").commit()
    mosfet_v1 = repo.new(branch="mosfet", structure=_mosfet(45), title="Grille 45nm", intent="reference").commit()

    recipe_variant = repo.derive(recipe_v1.id, title="Plus de farine", intent="essai")
    recipe_variant.structure.ingredients["farine"] = Quantity(value=240, unit="g")
    recipe_v2 = recipe_variant.commit()

    solar_v1 = repo.new(branch="solar", structure=_solar_module(0.5), title="Jonction de base", intent="reference").commit()

    mosfet_variant = repo.derive(mosfet_v1.id, title="Grille 32nm", intent="essai")
    mosfet_variant.structure.gate_length = Quantity(value=32, unit="nm")
    mosfet_v2 = mosfet_variant.commit()

    fondant_v1 = repo.new(branch="fondant", structure=_fondant(180), title="Fondant de base", intent="reference").commit()

    solar_variant = repo.derive(solar_v1.id, title="Jonction plus fine", intent="essai")
    solar_variant.structure.cells[0].junction.depletion_width = Quantity(value=0.3, unit="um")
    solar_v2 = solar_variant.commit()

    fondant_variant = repo.derive(fondant_v1.id, title="Plus de chocolat", intent="essai")
    fondant_variant.structure.dark_chocolate = Quantity(value=200, unit="g")
    fondant_v2 = fondant_variant.commit()

    return repo, {
        "recipe": (recipe_v1, recipe_v2),
        "mosfet": (mosfet_v1, mosfet_v2),
        "solar": (solar_v1, solar_v2),
        "fondant": (fondant_v1, fondant_v2),
    }


def test_all_eight_commits_and_four_branches_coexist():
    repo, domains = _build_multi_domain_repo()
    assert len(repo) == 8
    assert set(repo.branches) == {"recipe", "mosfet", "solar", "fondant"}
    for name, (_, v2) in domains.items():
        assert repo.branches[name] == v2.id


def test_each_branchs_history_contains_only_its_own_domain():
    repo, domains = _build_multi_domain_repo()
    for name, (v1, v2) in domains.items():
        history_ids = {e.id for e in repo.log(name)}
        assert history_ids == {v1.id, v2.id}
        other_ids = {e.id for other, (a, b) in domains.items() if other != name for e in (a, b)}
        assert history_ids.isdisjoint(other_ids)


def test_loading_a_structure_returns_the_exact_right_domain_class():
    repo, domains = _build_multi_domain_repo()
    expected_types = {
        "recipe": CakeRecipe,
        "mosfet": MOSFETStructure,
        "solar": SolarModule,
        "fondant": MoltenChocolateCake,
    }
    for name, (v1, _) in domains.items():
        structure = repo.load_structure(v1)
        assert type(structure) is expected_types[name]


def test_registry_resolves_every_domain_type_independently():
    # Committing several domains to one repo must not make Structure.resolve() confuse them -
    # each experiment's structure_type is its own fully-qualified registry key.
    repo, domains = _build_multi_domain_repo()
    keys = {name: v1.structure_type for name, (v1, _) in domains.items()}
    assert len(set(keys.values())) == 4  # all distinct
    assert Structure.resolve(keys["recipe"]) is CakeRecipe
    assert Structure.resolve(keys["mosfet"]) is MOSFETStructure
    assert Structure.resolve(keys["solar"]) is SolarModule
    assert Structure.resolve(keys["fondant"]) is MoltenChocolateCake


def test_diff_within_a_domain_is_unaffected_by_the_other_domains():
    repo, domains = _build_multi_domain_repo()
    recipe_v1, recipe_v2 = domains["recipe"]
    diff = repo.diff(recipe_v1.id, recipe_v2.id)
    assert diff.changed_paths == ["ingredients.farine"]

    mosfet_v1, mosfet_v2 = domains["mosfet"]
    diff = repo.diff(mosfet_v1.id, mosfet_v2.id)
    assert diff.changed_paths == ["gate_length"]


def test_cross_domain_diff_does_not_crash_it_is_just_meaningless():
    # Nothing stops you from diffing a recipe against a MOSFET - Follow has no domain
    # knowledge, so this must degrade gracefully (a big generic diff) rather than error out.
    repo, domains = _build_multi_domain_repo()
    recipe_v1, _ = domains["recipe"]
    mosfet_v1, _ = domains["mosfet"]
    diff = diff_structures(repo.load_structure(recipe_v1), repo.load_structure(mosfet_v1))
    assert len(diff) > 0
    kinds = {e.kind for e in diff}
    assert kinds <= {"added", "removed", "changed"}


def test_graph_includes_every_domain_and_renders_without_error():
    repo, domains = _build_multi_domain_repo()
    dag = repo.graph()
    assert len(dag) == 8
    for name, (v1, v2) in domains.items():
        assert dag[v2.id] == [v1.id]
        assert dag[v1.id] == []

    fig = build_graph_figure(repo)
    node_trace = fig.data[1]
    assert len(node_trace.x) == 8
    branch_trace = fig.data[2]
    assert set(branch_trace.text) == {"⌥ recipe", "⌥ mosfet", "⌥ solar", "⌥ fondant"}


def test_automatic_report_covers_every_domain_without_error():
    repo, domains = _build_multi_domain_repo()
    html = render_study_html(repo, embed_plotly=False)
    assert html.count("<div") == html.count("</div>")
    for _, (v1, v2) in domains.items():
        assert f'id="{v1.id}"' in html
        assert f'id="{v2.id}"' in html


def test_merging_within_one_domain_does_not_touch_the_others():
    repo, domains = _build_multi_domain_repo()
    recipe_v1, recipe_v2 = domains["recipe"]

    side = repo.derive(recipe_v1.id, new_branch="recipe-side", title="side", intent="x")
    side.structure.ingredients["farine"] = Quantity(value=210, unit="g")
    side_tip = side.commit()

    before_len = len(repo)
    repo.merge("recipe", side_tip.id, title="merge", intent="x", take_structure=["ingredients.farine"]).commit()

    assert len(repo) == before_len + 1
    # the other three domains' tips are untouched
    for name in ("mosfet", "solar", "fondant"):
        _, v2 = domains[name]
        assert repo.branches[name] == v2.id


def test_tags_across_domains_do_not_collide():
    repo, domains = _build_multi_domain_repo()
    for name, (v1, _) in domains.items():
        repo.tag(f"{name}-baseline", v1.id)

    assert len(repo.tags) == 4
    for name, (v1, _) in domains.items():
        assert repo.get(f"{name}-baseline").id == v1.id
