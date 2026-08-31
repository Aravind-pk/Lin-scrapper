"""Extractors must degrade to None, never raise — LinkedIn's response shape
varies with how complete a profile is."""

from app.linkedin.profile import (
    Profile,
    _date,
    _date_range,
    _image_url,
    _text,
    extract_profile,
)


def test_scalar_fields_extract(normalized_payload):
    p = extract_profile(normalized_payload)
    assert p.name == "Ada Lovelace"
    assert p.headline == "Analyst, Analytical Engine"
    assert p.location == "London, England, United Kingdom"
    assert p.about.startswith("Notes upon")
    assert p.profile_picture.endswith("800_800/photo.jpg")
    assert p.background_image.endswith("1584_396/cover.jpg")


def test_image_url_joins_root_and_largest_artifact(normalized_payload):
    """Neither half is a URL on its own, and the artifacts are unordered."""
    assert extract_profile(normalized_payload).profile_picture == (
        "https://media.licdn.com/dms/image/v2/SYNTHETIC/800_800/photo.jpg"
    )


# --- experience ---


def test_experience_extracts_in_order(normalized_payload):
    exp = extract_profile(normalized_payload).experience
    assert [e.title for e in exp] == ["Analyst", "Correspondent"]


def test_experience_reads_the_inline_company_name(normalized_payload):
    assert extract_profile(normalized_payload).experience[0].company == (
        "Analytical Engine Programme"
    )


def test_experience_falls_back_to_the_referenced_company(normalized_payload):
    """companyName is often absent; the Company entity carries the name."""
    assert extract_profile(normalized_payload).experience[1].company == "Royal Society"


def test_absent_end_date_means_current(normalized_payload):
    current = extract_profile(normalized_payload).experience[0]
    assert current.start_date == "1843-03"
    assert current.end_date is None
    assert current.is_current is True


def test_present_end_date_means_not_current(normalized_payload):
    past = extract_profile(normalized_payload).experience[1]
    assert (past.start_date, past.end_date) == ("1833-01", "1842-12")
    assert past.is_current is False


def test_experience_keeps_location_and_description(normalized_payload):
    e = extract_profile(normalized_payload).experience[0]
    assert e.location == "London, England, United Kingdom"
    assert e.description.startswith("Translated")


def test_employment_type_resolves_through_its_reference(normalized_payload):
    """Verified against a real response: employmentType is a reference to an
    EmploymentType entity carrying `name`, not an inline string."""
    assert extract_profile(normalized_payload).experience[0].employment_type == (
        "Full-time"
    )


def test_employment_type_absent_yields_none(normalized_payload):
    assert extract_profile(normalized_payload).experience[1].employment_type is None


# --- education, skills, certifications, languages ---


def test_education_extracts(normalized_payload):
    ed = extract_profile(normalized_payload).education[0]
    assert ed.school == "Private Tuition"
    assert ed.degree == "Mathematics"
    assert ed.field_of_study == "Mathematics and Logic"
    assert ed.activities == "Correspondence with De Morgan"


def test_year_only_dates_omit_the_month(normalized_payload):
    ed = extract_profile(normalized_payload).education[0]
    assert (ed.start_date, ed.end_date) == ("1829", "1835")


def test_skills_are_plain_strings(normalized_payload):
    assert extract_profile(normalized_payload).skills == ["Algorithms", "Mathematics"]


def test_blank_skills_are_dropped(normalized_payload):
    assert "" not in extract_profile(normalized_payload).skills
    assert "  " not in extract_profile(normalized_payload).skills


def test_certifications_extract(normalized_payload):
    c = extract_profile(normalized_payload).certifications[0]
    assert c.name == "Fellow of the Analytical Society"
    assert c.authority == "Analytical Society"
    assert c.license_number == "AS-1843"
    assert c.url.endswith("AS-1843")
    assert c.start_date == "1843-06"


def test_languages_extract_with_proficiency(normalized_payload):
    langs = extract_profile(normalized_payload).languages
    assert [(l.name, l.proficiency) for l in langs] == [
        ("English", "NATIVE_OR_BILINGUAL"),
        # Real profiles mostly leave this null even when the language is listed.
        ("French", None),
    ]


# --- date helpers ---


def test_date_formats_year_and_month():
    assert _date({"year": 2019, "month": 3}) == "2019-03"


def test_date_formats_year_alone():
    assert _date({"year": 2019}) == "2019"


def test_date_rejects_a_month_without_a_year():
    assert _date({"month": 3}) is None


def test_date_rejects_non_dicts():
    assert _date("2019") is None
    assert _date(None) is None


def test_date_range_of_a_non_dict_is_empty():
    assert _date_range("nope") == (None, None, False)


def test_date_range_without_a_start_is_not_current():
    assert _date_range({"end": {"year": 2020}}) == (None, "2020", False)


# --- degradation ---


def test_empty_payload_yields_an_all_none_profile():
    assert extract_profile({"data": {}, "included": []}) == Profile()


def test_missing_last_name_still_yields_a_name():
    payload = _profile_payload(firstName="Ada", lastName=None)
    assert extract_profile(payload).name == "Ada"


def test_missing_both_names_yields_none():
    payload = _profile_payload(firstName=None, lastName=None)
    assert extract_profile(payload).name is None


def test_blank_headline_becomes_none():
    payload = _profile_payload(headline="   ")
    assert extract_profile(payload).headline is None


def test_location_falls_back_to_location_name():
    payload = _profile_payload(locationName="Dublin, Ireland")
    assert extract_profile(payload).location == "Dublin, Ireland"


def test_missing_picture_yields_none():
    assert extract_profile(_profile_payload()).profile_picture is None


def test_missing_collections_yield_empty_lists():
    p = extract_profile({"data": {}, "included": []})
    assert (p.experience, p.education, p.skills) == ([], [], [])
    assert (p.certifications, p.languages) == ([], [])


def _picture(**vector):
    return {"displayImageReference": {"vectorImage": vector}}


def test_picture_without_root_url_yields_none():
    assert _image_url(
        _picture(artifacts=[{"width": 1, "fileIdentifyingUrlPathSegment": "a.jpg"}])
    ) is None


def test_picture_with_empty_artifacts_yields_none():
    assert _image_url(_picture(rootUrl="https://x/", artifacts=[])) is None


def test_picture_handles_artifacts_missing_a_width():
    url = _image_url(
        _picture(
            rootUrl="https://x/",
            artifacts=[{"fileIdentifyingUrlPathSegment": "a.jpg"}],
        )
    )
    assert url == "https://x/a.jpg"


def test_picture_without_a_path_segment_yields_none():
    assert _image_url(
        _picture(rootUrl="https://x/", artifacts=[{"width": 400}])
    ) is None


def test_image_url_rejects_non_dicts():
    assert _image_url("nope") is None
    assert _image_url(None) is None


def test_text_unwraps_attributed_strings():
    assert _text({"text": "About me"}) == "About me"


def test_text_rejects_non_strings():
    assert _text(42) is None
    assert _text(None) is None
    assert _text([]) is None


def test_extraction_never_raises_on_malformed_entities():
    payload = {
        "data": {"*elements": ["urn:li:fsd_profile:x"]},
        "included": [
            {
                "entityUrn": "urn:li:fsd_profile:x",
                "$type": "com.linkedin.voyager.dash.identity.profile.Profile",
                "firstName": [],
                "headline": 7,
                "geoLocation": "not-a-dict",
                "profilePicture": ["nope"],
            }
        ],
    }
    assert extract_profile(payload) == Profile()


def test_malformed_collections_do_not_raise():
    payload = _profile_payload(
        profilePositions="not-a-collection",
        profileEducations={"elements": ["not-a-dict", 7]},
        profileSkills={"elements": [{"name": None}]},
    )
    p = extract_profile(payload)
    assert p.education == [] and p.skills == []


def _profile_payload(**fields) -> dict:
    entity = {
        "entityUrn": "urn:li:fsd_profile:x",
        "$type": "com.linkedin.voyager.dash.identity.profile.Profile",
    }
    entity.update({k: v for k, v in fields.items() if v is not None})
    return {"data": {"*elements": ["urn:li:fsd_profile:x"]}, "included": [entity]}
