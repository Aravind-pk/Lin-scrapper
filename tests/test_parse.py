from app.linkedin.parse import (
    _MAX_DEPTH,
    build_index,
    entities_of_type,
    find_elements,
    resolve,
    root_profile,
)

PROFILE_URN = "urn:li:fsd_profile:ACoAAASynthetic"


def test_index_is_keyed_by_entity_urn(normalized_payload):
    index = build_index(normalized_payload)
    assert PROFILE_URN in index
    # Derived, not hardcoded — the fixture grows as extractors are added.
    assert len(index) == sum(
        1 for e in normalized_payload["included"] if e.get("entityUrn")
    )


def test_index_of_a_payload_without_included_is_empty():
    assert build_index({"data": {}}) == {}


def test_star_prefix_is_stripped_from_resolved_keys(normalized_payload):
    profile = root_profile(normalized_payload)
    assert "geoLocation" in profile
    assert "*geoLocation" not in profile


def test_references_resolve_into_entities(normalized_payload):
    profile = root_profile(normalized_payload)
    assert profile["geoLocation"]["geo"]["defaultLocalizedName"].startswith("London")


def test_dangling_reference_resolves_to_none(normalized_payload):
    """Real captures contain plenty; raising would fail ordinary profiles."""
    assert root_profile(normalized_payload)["profileProjects"] is None


def test_self_reference_is_broken_by_the_cycle_guard(normalized_payload):
    assert root_profile(normalized_payload)["self"] is None


def test_two_hop_cycle_is_broken(normalized_payload):
    """geo points back at the geoLocation that reached it."""
    profile = root_profile(normalized_payload)
    assert profile["geoLocation"]["geo"]["owner"] is None


def test_non_urn_strings_pass_through(normalized_payload):
    index = build_index(normalized_payload)
    assert resolve("just a string", index, is_ref=True) == "just a string"


def test_unknown_urn_in_reference_position_resolves_to_none(normalized_payload):
    index = build_index(normalized_payload)
    assert resolve("urn:li:fsd_profile:nope", index, is_ref=True) is None


def test_urn_outside_reference_position_is_left_alone():
    """entityUrn is an identity field, not a reference. Resolving it would
    erase every entity's own identity."""
    index = {"urn:li:x:1": {"entityUrn": "urn:li:x:1", "v": 1}}
    assert resolve({"entityUrn": "urn:li:x:1"}, index) == {"entityUrn": "urn:li:x:1"}


def test_resolved_entities_keep_their_entity_urn(normalized_payload):
    profile = root_profile(normalized_payload)
    assert profile["entityUrn"] == PROFILE_URN
    assert profile["geoLocation"]["entityUrn"] == "urn:li:fsd_geoLocation:synthetic"


def test_scalars_pass_through():
    assert resolve(42, {}) == 42
    assert resolve(None, {}) is None
    assert resolve(True, {}) is True


def test_lists_under_a_reference_key_resolve_elementwise():
    index = {"urn:li:x:1": {"entityUrn": "urn:li:x:1", "v": 1}}
    resolved = resolve({"*items": ["urn:li:x:1", "urn:li:x:missing"]}, index)
    assert resolved["items"] == [{"entityUrn": "urn:li:x:1", "v": 1}, None]


def test_depth_cap_stops_runaway_nesting():
    node = current = {}
    for _ in range(_MAX_DEPTH + 5):
        current["next"] = {}
        current = current["next"]
    current["leaf"] = "deep"
    resolved = resolve(node, {})
    assert resolved is not None


def test_entities_of_type_filters_by_suffix(normalized_payload):
    index = build_index(normalized_payload)
    assert len(entities_of_type(index, ".identity.profile.Profile")) == 1
    assert entities_of_type(index, ".does.not.Exist") == []


def test_find_elements_locates_a_nested_finder_result():
    nested = {"data": {"identityDashProfilesByMemberIdentity": {"*elements": ["a"]}}}
    assert find_elements(nested) == ["a"]


def test_find_elements_returns_none_when_absent():
    assert find_elements({"data": {"paging": {}}}) is None


def test_root_profile_falls_back_to_included_when_data_is_empty(normalized_payload):
    payload = {"data": {}, "included": normalized_payload["included"]}
    assert root_profile(payload)["firstName"] == "Ada"


def test_root_profile_returns_none_for_an_empty_payload():
    assert root_profile({"data": {}, "included": []}) is None
