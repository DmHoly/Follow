import pytest

from examples.recipe import BakeStep, CakeRecipe
from follow import ExperimentNotFoundError, FollowError, Quantity, Repository
from follow.storage import JsonFileStore, MemoryStore, ObjectStore


def _cake(flour_g: float) -> CakeRecipe:
    return CakeRecipe(
        name="Vanilla cake",
        ingredients={"flour": Quantity(value=flour_g, unit="g"), "sugar": Quantity(value=150, unit="g")},
        bake=BakeStep(temperature=Quantity(value=180, unit="C"), duration=Quantity(value=35, unit="min")),
    )


def _baseline(repo: Repository, *, flour_g: float = 200, title: str = "Baseline vanilla cake"):
    return (
        repo.new(branch="main", structure=_cake(flour_g), title=title, intent="Establish a reference bake")
        .add_objective(name="rise", metric="height_cm", direction="maximize", target=5.0)
        .commit()
    )


def test_commit_computes_a_stable_content_id():
    # This test's name promised stability and content addressing; it used to assert only that the
    # id started with "exp_", which an entirely random id would also satisfy. Both halves of the
    # promise are checked now: same content, same id - different content, different id.
    first = _baseline(Repository())
    again = _baseline(Repository())
    assert first.id == again.id

    other_structure = _baseline(Repository(), flour_g=240)
    other_title = _baseline(Repository(), title="Something else")
    assert len({first.id, other_structure.id, other_title.id}) == 3

    assert first.id.startswith("exp_")
    assert first.parents == []


def test_a_committed_id_survives_a_reload(tmp_path):
    repo = Repository(tmp_path)
    committed = _baseline(repo)
    assert Repository(tmp_path).get("main").id == committed.id


def test_derive_carries_over_config_and_adds_a_baseline_reference():
    repo = Repository()
    baseline = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="Reference bake").commit()

    variant = (
        repo.derive(baseline.id, title="More flour", intent="Does more flour improve the rise?")
    )
    variant.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    committed = variant.commit()

    assert committed.parents == [baseline.id]
    assert any(r.role == "baseline" and r.experiment_id == baseline.id for r in committed.references)
    assert committed.objectives == baseline.objectives


def test_diff_between_baseline_and_derived_experiment():
    repo = Repository()
    baseline = repo.new(branch="main", structure=_cake(200), title="Baseline", intent="Reference bake").commit()

    variant_builder = repo.derive(baseline.id, title="More flour", intent="More flour")
    variant_builder.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    variant = variant_builder.commit()

    diff = repo.diff(baseline.id, variant.id)
    assert diff.changed_paths == ["ingredients.flour"]


def test_log_walks_first_parent_history_newest_first():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    v2 = repo.derive(v1.id, title="v2", intent="tweak").commit()
    v3 = repo.derive(v2.id, title="v3", intent="tweak again").commit()

    history_ids = [exp.id for exp in repo.log("main")]
    assert history_ids == [v3.id, v2.id, v1.id]


def test_branching_forks_without_disturbing_the_original_branch():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    experimental = repo.derive(v1.id, new_branch="less-sugar", title="Less sugar", intent="Try less sugar").commit()

    assert repo.branches["main"] == v1.id
    assert repo.branches["less-sugar"] == experimental.id


def test_tag_and_unknown_ref_lookup():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    repo.tag("champion", v1.id)

    assert repo.get("champion").id == v1.id
    with pytest.raises(ExperimentNotFoundError):
        repo.get("does-not-exist")


def test_persistence_round_trips_through_json_files(tmp_path):
    repo = Repository(tmp_path)
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    repo.derive(v1.id, title="v2", intent="tweak").commit()

    reloaded = Repository(tmp_path)
    assert len(reloaded) == 2
    assert reloaded.get("main").title == "v2"
    assert [e.id for e in reloaded.log("main")] == [e.id for e in repo.log("main")]


def test_contains_operator():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()

    assert v1.id in repo
    assert "main" in repo
    assert "does-not-exist" not in repo


def test_diff_from_baseline_on_the_builder_before_commit():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()

    root_builder = repo.new(branch="side", structure=_cake(200), title="root", intent="no baseline")
    assert root_builder.diff_from_baseline() is None

    variant = repo.derive(v1.id, title="v2", intent="more flour")
    variant.structure.ingredients["flour"] = Quantity(value=240, unit="g")
    diff = variant.diff_from_baseline()
    assert diff is not None
    assert diff.changed_paths == ["ingredients.flour"]


def test_branch_and_tag_persist_to_disk_when_called_directly(tmp_path):
    repo = Repository(tmp_path)
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    v2 = repo.derive(v1.id, title="v2", intent="tweak").commit()

    repo.branch("stable", v1.id)
    repo.tag("first-release", v1.id)

    reloaded = Repository(tmp_path)
    assert reloaded.branches["stable"] == v1.id
    assert reloaded.tags["first-release"] == v1.id
    assert reloaded.branches["main"] == v2.id


def test_tags_are_descriptive_labels_and_do_not_create_repository_refs():
    # Regression: an experiment's `tags` used to be promoted to repository tags, i.e. immutable
    # refs. A label is not a ref: it is reused across experiments by nature, and promoting it
    # made the second commit carrying it fail outright.
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start", tags=["milestone"]).commit()

    assert v1.tags == ["milestone"]  # stored on the experiment...
    assert repo.tags == {}  # ...without becoming a ref
    with pytest.raises(ExperimentNotFoundError):
        repo.get("milestone")


def test_the_same_label_can_be_reused_on_several_experiments():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start", tags=["à refaire"]).commit()
    v2 = repo.new(branch="side", structure=_cake(220), title="v2", intent="start", tags=["à refaire"]).commit()

    assert [e.id for e in repo if "à refaire" in e.tags] == [v1.id, v2.id]


def test_a_repository_tag_is_created_explicitly_and_stays_immutable():
    # the other half of the split: repo.tag() is what makes a citable pointer, and it keeps the
    # immutability guarantee that made labels-as-refs unworkable in the first place
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start", tags=["milestone"]).commit()
    v2 = repo.derive(v1.id, title="v2", intent="tweak").commit()

    repo.tag("milestone", v1.id)
    assert repo.get("milestone").id == v1.id
    with pytest.raises(FollowError, match="immutable"):
        repo.tag("milestone", v2.id)


def test_baseline_follows_the_immediate_parent_across_a_chain_of_derives():
    # Regression: derive() used to carry the parent's own baseline over and then skip adding a
    # new one ("unless one is already present"), so from the third generation on every derived
    # experiment still pointed its baseline at the root - and diff_from_baseline compared
    # against the wrong ancestor without a word.
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()

    b2 = repo.derive(v1.id, title="v2", intent="more flour")
    b2.structure.ingredients["flour"] = Quantity(value=220, unit="g")
    v2 = b2.commit()

    b3 = repo.derive(v2.id, title="v3", intent="even more flour")
    b3.structure.ingredients["flour"] = Quantity(value=240, unit="g")

    baselines = [r.experiment_id for r in b3.references if r.role == "baseline"]
    assert baselines == [v2.id]  # the immediate parent, exactly once

    diff = b3.diff_from_baseline()
    assert diff.entries[0].before["value"] == 220  # vs v2, not vs v1's 200
    assert diff.entries[0].after["value"] == 240

    v3 = b3.commit()
    assert [r.experiment_id for r in v3.references if r.role == "baseline"] == [v2.id]


def test_derive_keeps_non_lineage_references_but_drops_the_parents_own():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()

    b2 = repo.derive(v1.id, title="v2", intent="tweak")
    b2.add_reference(role="target_spec", label="spec du client", external_source="doi://10.1/spec")
    v2 = b2.commit()

    b3 = repo.derive(v2.id, title="v3", intent="tweak again")
    roles = [(r.role, r.experiment_id or r.external_source) for r in b3.references]
    assert ("target_spec", "doi://10.1/spec") in roles  # carried over, as before
    assert ("baseline", v1.id) not in roles  # the parent's own lineage is not inherited
    assert [r.experiment_id for r in b3.references if r.role == "baseline"] == [v2.id]


def test_deriving_from_a_merge_commit_does_not_inherit_its_merge_source():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    side = repo.derive(v1.id, new_branch="side", title="side", intent="explore")
    side.structure.ingredients["flour"] = Quantity(value=300, unit="g")
    side_tip = side.commit()
    merged = repo.merge("main", side_tip.id, title="merge", intent="merge", take_structure=["ingredients.flour"]).commit()

    after_merge = repo.derive(merged.id, title="suite", intent="continue")
    roles = {r.role for r in after_merge.references}
    assert "merge_source" not in roles  # that pointer described the merge, not this commit
    assert [r.experiment_id for r in after_merge.references if r.role == "baseline"] == [merged.id]


def test_carry_references_false_still_gets_a_baseline():
    repo = Repository()
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="start").commit()
    b2 = repo.derive(v1.id, title="v2", intent="tweak", carry_references=False)
    assert [r.experiment_id for r in b2.references if r.role == "baseline"] == [v1.id]


# -- persistence is a collaborator, not part of the class ---------------------------------------


class _RecordingStore(ObjectStore):
    """A backend written entirely from outside the library - the point of the abstraction."""

    def __init__(self):
        self.experiments: dict = {}
        self.branches: dict = {}
        self.tags: dict = {}
        self.writes: list = []

    def load(self):
        return dict(self.experiments), dict(self.branches), dict(self.tags)

    def add_experiment(self, experiment):
        self.writes.append(("add_experiment", experiment.id))
        self.experiments[experiment.id] = experiment

    def write_refs(self, branches, tags):
        self.writes.append(("write_refs", dict(branches)))
        self.branches, self.tags = dict(branches), dict(tags)


def test_a_repository_can_be_given_any_object_store():
    store = _RecordingStore()
    repo = Repository(store=store)
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="x").commit()
    v2 = repo.derive(v1.id, title="v2", intent="x").commit()

    assert [kind for kind, _ in store.writes] == ["add_experiment", "write_refs"] * 2
    assert store.branches == {"main": v2.id}

    reopened = Repository(store=store)  # a second repository over the same backend
    assert len(reopened) == 2
    assert reopened.get("main").title == "v2"


def test_moving_a_ref_reaches_the_store_without_a_commit():
    store = _RecordingStore()
    repo = Repository(store=store)
    v1 = repo.new(branch="main", structure=_cake(200), title="v1", intent="x").commit()
    store.writes.clear()

    repo.tag("release", v1.id)
    assert store.writes == [("write_refs", {"main": v1.id})]
    assert store.tags == {"release": v1.id}


def test_an_in_memory_repository_uses_the_memory_store():
    # not a stand-in for the real thing: it is the backend Repository() genuinely runs on
    assert isinstance(Repository()._store, MemoryStore)
    assert isinstance(Repository(store=None)._store, MemoryStore)


def test_a_path_selects_the_json_backend(tmp_path):
    repo = Repository(tmp_path)
    assert isinstance(repo._store, JsonFileStore)
    repo.new(branch="main", structure=_cake(200), title="v1", intent="x").commit()
    assert (tmp_path / "refs.json").exists()
    assert list((tmp_path / "objects").glob("*.json"))


def test_passing_both_a_path_and_a_store_is_refused():
    with pytest.raises(FollowError, match="not both"):
        Repository("/tmp/somewhere", store=_RecordingStore())
