from follow.merging import resolve_merge_paths


def test_untouched_paths_keep_ours_value():
    ours = {"a": 1, "b": {"c": 2}}
    theirs = {"a": 99, "b": {"c": 99}}
    merged = resolve_merge_paths(ours, theirs, [])
    assert merged == ours
    assert merged is not ours  # deep-copied, mutating the result must not touch `ours`


def test_take_a_single_leaf_from_theirs():
    ours = {"a": 1, "b": {"c": 2}}
    theirs = {"a": 99, "b": {"c": 99}}
    merged = resolve_merge_paths(ours, theirs, ["b.c"])
    assert merged == {"a": 1, "b": {"c": 99}}


def test_take_a_whole_list_element_from_theirs():
    ours = [{"name": "mix"}, {"name": "bake", "temp": 170}, {"name": "cool"}]
    theirs = [{"name": "mix"}, {"name": "bake", "temp": 175}, {"name": "cool"}]
    merged = resolve_merge_paths(ours, theirs, ["[1]"])
    assert merged[1] == {"name": "bake", "temp": 175}
    assert merged[0] == ours[0]
    assert merged[2] == ours[2]


def test_take_a_nested_field_inside_a_list_element():
    ours = [{"name": "bake", "temp": 170, "duration": 35}]
    theirs = [{"name": "bake", "temp": 175, "duration": 32}]
    merged = resolve_merge_paths(ours, theirs, ["[0].temp"])
    assert merged == [{"name": "bake", "temp": 175, "duration": 35}]
