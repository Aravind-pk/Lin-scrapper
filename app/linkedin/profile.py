"""Field extraction and the response schema.

Every extractor is defensive: a field LinkedIn omits yields None or an empty
list rather than an exception, because the response shape varies with how
complete a profile is.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from app.linkedin.constants import DECORATION_ID
from app.linkedin.parse import build_index, entities_of_type, resolve, root_profile


class Experience(BaseModel):
    title: str | None = None
    company: str | None = None
    employment_type: str | None = None
    location: str | None = None
    description: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    is_current: bool = False


class Education(BaseModel):
    school: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    description: str | None = None
    activities: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class Certification(BaseModel):
    name: str | None = None
    authority: str | None = None
    license_number: str | None = None
    url: str | None = None
    start_date: str | None = None
    end_date: str | None = None


class Language(BaseModel):
    name: str | None = None
    proficiency: str | None = None


class Profile(BaseModel):
    name: str | None = None
    headline: str | None = None
    location: str | None = None
    about: str | None = None
    profile_picture: str | None = None
    background_image: str | None = None
    experience: list[Experience] = Field(default_factory=list)
    education: list[Education] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[Certification] = Field(default_factory=list)
    languages: list[Language] = Field(default_factory=list)


class Meta(BaseModel):
    source: str = "voyager-dash-profiles"
    decoration_id: str = DECORATION_ID
    fetched_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    duration_ms: int | None = None


class ProfileResponse(BaseModel):
    profile: Profile
    meta: Meta


def extract_profile(payload: dict[str, Any]) -> Profile:
    entity = root_profile(payload) or {}
    index = build_index(payload)
    return Profile(
        name=_name(entity),
        headline=_text(entity.get("headline")),
        location=_location(entity),
        about=_text(entity.get("summary")),
        profile_picture=_image_url(entity.get("profilePicture")),
        background_image=_image_url(entity.get("backgroundPicture")),
        experience=_experience(entity, index),
        education=_education(entity, index),
        skills=_skills(entity, index),
        certifications=_certifications(entity, index),
        languages=_languages(entity, index),
    )


# --- scalar fields -----------------------------------------------------------


def _name(entity: dict[str, Any]) -> str | None:
    parts = [_text(entity.get("firstName")), _text(entity.get("lastName"))]
    joined = " ".join(p for p in parts if p)
    return joined or None


def _location(entity: dict[str, Any]) -> str | None:
    geo = entity.get("geoLocation")
    if isinstance(geo, dict):
        place = geo.get("geo")
        if isinstance(place, dict):
            name = _text(place.get("defaultLocalizedName"))
            if name:
                return name
    return _text(entity.get("locationName")) or _text(entity.get("geoLocationName"))


def _image_url(picture: Any) -> str | None:
    """Largest available rendition of a profile or background image.

    The image is stored split: a rootUrl plus artifacts holding only the
    trailing path segment. Neither half is a URL on its own, and the artifacts
    are unordered, so the largest must be selected rather than assumed last.
    """
    if not isinstance(picture, dict):
        return None
    display = picture.get("displayImageReference") or picture.get("displayImage")
    vector = None
    if isinstance(display, dict):
        vector = display.get("vectorImage") or display
    if not isinstance(vector, dict):
        return None

    root = _text(vector.get("rootUrl"))
    artifacts = vector.get("artifacts")
    if not root or not isinstance(artifacts, list) or not artifacts:
        return None

    largest = max(
        (a for a in artifacts if isinstance(a, dict)),
        key=lambda a: a.get("width") or 0,
        default=None,
    )
    if not largest:
        return None
    segment = _text(largest.get("fileIdentifyingUrlPathSegment"))
    return f"{root}{segment}" if segment else None


# --- entity collections ------------------------------------------------------


def _experience(entity: dict[str, Any], index: dict) -> list[Experience]:
    positions = _related(entity, index, "profilePositions", ".profile.Position")
    if not positions:
        # Some decorations nest positions one level deeper, grouped by company.
        for group in _related(
            entity, index, "profilePositionGroups", ".profile.PositionGroup"
        ):
            positions.extend(
                _elements(group.get("profilePositionInPositionGroup"))
            )

    out = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        start, end, current = _date_range(p.get("dateRange"))
        out.append(
            Experience(
                title=_text(p.get("title")),
                company=_text(p.get("companyName")) or _named(p.get("company")),
                employment_type=_named(p.get("employmentType")),
                location=_text(p.get("locationName"))
                or _text(p.get("geoLocationName")),
                description=_text(p.get("description")),
                start_date=start,
                end_date=end,
                is_current=current,
            )
        )
    return out


def _education(entity: dict[str, Any], index: dict) -> list[Education]:
    out = []
    for e in _related(entity, index, "profileEducations", ".profile.Education"):
        start, end, _ = _date_range(e.get("dateRange"))
        out.append(
            Education(
                school=_text(e.get("schoolName")) or _named(e.get("school")),
                degree=_text(e.get("degreeName")),
                field_of_study=_text(e.get("fieldOfStudy")),
                description=_text(e.get("description")),
                activities=_text(e.get("activities")),
                start_date=start,
                end_date=end,
            )
        )
    return out


def _skills(entity: dict[str, Any], index: dict) -> list[str]:
    names = [
        _text(s.get("name"))
        for s in _related(entity, index, "profileSkills", ".profile.Skill")
    ]
    return [n for n in names if n]


def _certifications(entity: dict[str, Any], index: dict) -> list[Certification]:
    out = []
    for c in _related(
        entity, index, "profileCertifications", ".profile.Certification"
    ):
        start, end, _ = _date_range(c.get("dateRange"))
        out.append(
            Certification(
                name=_text(c.get("name")),
                authority=_text(c.get("authority"))
                or _named(c.get("company")),
                license_number=_text(c.get("licenseNumber")),
                url=_text(c.get("url")),
                start_date=start,
                end_date=end,
            )
        )
    return out


def _languages(entity: dict[str, Any], index: dict) -> list[Language]:
    return [
        Language(
            name=_text(lang.get("name")),
            proficiency=_text(lang.get("proficiency")),
        )
        for lang in _related(entity, index, "profileLanguages", ".profile.Language")
    ]


# --- helpers -----------------------------------------------------------------


def _related(
    entity: dict[str, Any], index: dict, key: str, type_suffix: str
) -> list[dict[str, Any]]:
    """Entities reached from the profile, or failing that, scanned by type.

    Navigating from the profile is correctly scoped. The type scan is a
    fallback for decorations that omit the reference — `included` holds only
    this profile's entities, so it stays accurate.
    """
    items = _elements(entity.get(key))
    if items:
        return items
    return [
        resolve(e, index, seen=frozenset({e.get("entityUrn", "")}))
        for e in entities_of_type(index, type_suffix)
    ]


def _elements(node: Any) -> list[dict[str, Any]]:
    """Unwrap a Voyager collection into its elements."""
    if isinstance(node, dict):
        node = node.get("elements")
    if not isinstance(node, list):
        return []
    return [item for item in node if isinstance(item, dict)]


def _date_range(node: Any) -> tuple[str | None, str | None, bool]:
    """(start, end, is_current) as ISO-ish strings: 2019-03, or 2019."""
    if not isinstance(node, dict):
        return None, None, False
    start = _date(node.get("start"))
    end = _date(node.get("end"))
    # An absent end on a present start is LinkedIn's way of saying "current".
    return start, end, bool(start) and end is None


def _date(node: Any) -> str | None:
    if not isinstance(node, dict):
        return None
    year, month = node.get("year"), node.get("month")
    if not isinstance(year, int):
        return None
    return f"{year:04d}-{month:02d}" if isinstance(month, int) else f"{year:04d}"


def _named(node: Any) -> str | None:
    """The `name` of a referenced entity (company, school, employment type)."""
    return _text(node.get("name")) if isinstance(node, dict) else None


def _text(value: Any) -> str | None:
    """Unwrap LinkedIn's several shapes for a string field."""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        # Attributed text: the rendered string sits under `text`.
        return _text(value.get("text"))
    return None
