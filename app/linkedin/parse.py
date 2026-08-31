"""Resolution of LinkedIn's normalized+json responses.

The response is a graph, not a tree: a small `data` root plus a flat
`included[]` of ~113 entities that reference each other by `entityUrn`. Keys
prefixed with `*` hold references rather than values.
"""

from __future__ import annotations

from typing import Any

_MAX_DEPTH = 12

_URN_PREFIX = "urn:li:"


def build_index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map entityUrn -> entity for everything in `included`."""
    index: dict[str, dict[str, Any]] = {}
    for entity in payload.get("included") or []:
        urn = entity.get("entityUrn")
        if urn:
            index[urn] = entity
    return index


def resolve(
    node: Any,
    index: dict[str, dict[str, Any]],
    depth: int = 0,
    seen: frozenset[str] = frozenset(),
    is_ref: bool = False,
) -> Any:
    """Expand references in `node` into the entities they point at.

    Only a `*`-prefixed key holds a reference. Plain urn strings such as
    `entityUrn` are identity fields and must survive untouched — resolving
    them would erase every entity's own identity.

    Dangling references resolve to None; real captures contain plenty, and
    raising on them would make the parser fail on ordinary profiles.
    """
    if depth >= _MAX_DEPTH:
        return node

    if isinstance(node, str):
        return _resolve_ref(node, index, depth, seen) if is_ref else node

    if isinstance(node, list):
        return [resolve(item, index, depth + 1, seen, is_ref) for item in node]

    if isinstance(node, dict):
        resolved: dict[str, Any] = {}
        for key, value in node.items():
            ref = key.startswith("*")
            # The * marks the key as a reference and is not part of the name.
            resolved[key[1:] if ref else key] = resolve(
                value, index, depth + 1, seen, ref
            )
        return resolved

    return node


def _resolve_ref(
    value: str,
    index: dict[str, dict[str, Any]],
    depth: int,
    seen: frozenset[str],
) -> Any:
    if not value.startswith(_URN_PREFIX):
        return value
    if value in seen:
        # Cycle. Without this guard resolution never terminates — profile
        # entities routinely reference each other both ways.
        return None
    entity = index.get(value)
    if entity is None:
        return None
    return resolve(entity, index, depth + 1, seen | {value})


def entities_of_type(
    index: dict[str, dict[str, Any]], type_suffix: str
) -> list[dict[str, Any]]:
    """Every included entity whose $type ends with `type_suffix`."""
    return [
        entity
        for entity in index.values()
        if str(entity.get("$type", "")).endswith(type_suffix)
    ]


def find_elements(node: Any, depth: int = 0) -> list[Any] | None:
    """First `*elements`/`elements` list anywhere under `data`.

    Voyager nests the finder result differently across response shapes, so
    search rather than assume a path.
    """
    if depth >= _MAX_DEPTH or not isinstance(node, dict):
        return None
    for key in ("*elements", "elements"):
        value = node.get(key)
        if isinstance(value, list) and value:
            return value
    for value in node.values():
        found = find_elements(value, depth + 1)
        if found:
            return found
    return None


def root_profile(payload: dict[str, Any]) -> dict[str, Any] | None:
    """The Profile entity the response is about.

    `data` points at it by urn; if that is missing, fall back to the sole
    Profile entity in `included`.
    """
    index = build_index(payload)

    elements = find_elements(payload.get("data") or {})
    if elements:
        first = elements[0]
        if isinstance(first, str):
            resolved = _resolve_ref(first, index, 0, frozenset())
            if isinstance(resolved, dict):
                return resolved
        elif isinstance(first, dict):
            return resolve(first, index)

    profiles = entities_of_type(index, ".identity.profile.Profile")
    if profiles:
        urn = profiles[0].get("entityUrn", "")
        return resolve(profiles[0], index, 0, frozenset({urn}) if urn else frozenset())
    return None
