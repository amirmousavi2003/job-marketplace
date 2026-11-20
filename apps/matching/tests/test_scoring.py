import itertools
import random

import pytest

from apps.matching import scoring
from apps.matching.features import PostFeatures, ResumeFeatures

pytestmark = pytest.mark.django_db


def rf(**kw):
    base = dict(
        skills=(),
        title_terms=(),
        experience_level="",
        highest_degree=-1,
        work_modes=(),
        province="",
        city="",
        expected_salary=None,
        text_parts=(),
    )
    return ResumeFeatures(**{**base, **kw})


def pf(**kw):
    base = dict(
        post_id=1,
        post_type="EMPLOYMENT",
        title="",
        title_norm="",
        required_skills=(),
        optional_skills=(),
        work_mode="REMOTE",
        province="",
        city="",
        required_experience="",
        required_degree=-1,
        salary_min=None,
        salary_max=None,
        text_parts=(),
    )
    return PostFeatures(**{**base, **kw})


def codes(result):
    return [r["code"] for r in result.reasons]


def only(result, factor):
    return result.factors[factor]


# ------------------------------------------------------------------ skills
def test_skills_full_partial_and_none():
    post = pf(required_skills=((1, "جنگو", ""), (2, "ری‌اکت", "")))
    full = scoring.score_pair(rf(skills=((1, "جنگو", "EXPERT"), (2, "ری‌اکت", "BEGINNER"))), post)
    half = scoring.score_pair(rf(skills=((1, "جنگو", "EXPERT"),)), post)
    none = scoring.score_pair(rf(skills=((9, "فتوشاپ", "EXPERT"),)), post)
    assert (full.score, half.score, none.score) == (100, 50, 0)
    assert "SKILL_OVERLAP_STRONG" in codes(full) and "SKILL_OVERLAP_PARTIAL" in codes(half)
    assert "SKILL_OVERLAP_NONE" in codes(none)
    missing = next(r for r in half.reasons if r["code"] == "MISSING_REQUIRED_SKILLS")
    assert missing["params"]["skills"] == ["ری‌اکت"] and "ری‌اکت" in missing["text_fa"]


def test_minimum_level_gives_half_credit():
    post = pf(required_skills=((1, "جنگو", "ADVANCED"),))
    assert scoring.score_pair(rf(skills=((1, "جنگو", "BEGINNER"),)), post).score == 50
    assert scoring.score_pair(rf(skills=((1, "جنگو", "EXPERT"),)), post).score == 100


def test_required_skills_weigh_more_than_optional_ones():
    post = pf(required_skills=((1, "الف", ""),), optional_skills=((2, "ب", ""),))
    has_required = scoring.score_pair(rf(skills=((1, "الف", "EXPERT"),)), post)
    has_optional = scoring.score_pair(rf(skills=((2, "ب", "EXPERT"),)), post)
    assert (has_required.score, has_optional.score) == (80, 20)


def test_post_without_skills_leaves_the_factor_out():
    assert only(scoring.score_pair(rf(skills=((1, "x", "EXPERT"),)), pf()), "skills") == {
        "applicable": False
    }


# ------------------------------------------------------------------ other factors
def test_title_match_levels():
    post = pf(title="برنامه‌نویس جنگو", title_norm="برنامه نویس جنگو")
    assert scoring.score_pair(rf(title_terms=("برنامه نویس جنگو",)), post).score == 100
    assert scoring.score_pair(rf(title_terms=("برنامه نویس",)), post).score == 100  # contained
    assert scoring.score_pair(rf(title_terms=("برنامه نویس وب",)), post).score == 67  # 2 of 3 words
    assert scoring.score_pair(rf(title_terms=("حسابدار",)), post).score == 0
    assert only(scoring.score_pair(rf(), post), "title") == {"applicable": False}


@pytest.mark.parametrize(
    ("mine", "needed", "expected", "code"),
    [
        ("SENIOR", "MID", 100, "EXPERIENCE_MEETS"),
        ("MID", "MID", 100, "EXPERIENCE_MEETS"),
        ("JUNIOR", "MID", 50, "EXPERIENCE_ONE_LEVEL_BELOW"),
        ("NO_EXPERIENCE", "MID", 0, "EXPERIENCE_FAR_BELOW"),
    ],
)
def test_experience_ladder(mine, needed, expected, code):
    result = scoring.score_pair(rf(experience_level=mine), pf(required_experience=needed))
    assert result.score == expected and code in codes(result)


def test_experience_is_not_used_for_projects_or_when_unknown():
    assert not only(
        scoring.score_pair(
            rf(experience_level="MID"), pf(post_type="PROJECT", required_experience="SENIOR")
        ),
        "experience",
    ).get("applicable")
    assert not only(scoring.score_pair(rf(), pf(required_experience="MID")), "experience").get(
        "applicable"
    )


def test_education_levels_and_unknown_is_not_penalized():
    assert scoring.score_pair(rf(highest_degree=4), pf(required_degree=3)).score == 100
    assert scoring.score_pair(rf(highest_degree=2), pf(required_degree=3)).score == 50
    assert scoring.score_pair(rf(highest_degree=0), pf(required_degree=3)).score == 0
    unknown = scoring.score_pair(rf(), pf(required_degree=3, required_experience="MID"))
    assert (
        "EDUCATION_NOT_PROVIDED" in codes(unknown)
        and only(unknown, "education")["applicable"] is False
    )


def test_work_mode_including_partial_hybrid():
    assert scoring.score_pair(rf(work_modes=("REMOTE",)), pf(work_mode="REMOTE")).score == 100
    assert scoring.score_pair(rf(work_modes=("REMOTE",)), pf(work_mode="HYBRID")).score == 50
    bad = scoring.score_pair(rf(work_modes=("REMOTE",)), pf(work_mode="ON_SITE"))
    assert bad.score == 0 and "WORK_MODE_INCOMPATIBLE" in codes(bad)
    assert only(scoring.score_pair(rf(), pf()), "work_mode") == {"applicable": False}


def test_location_levels_and_remote_is_exempt():
    onsite = dict(work_mode="ON_SITE", province="فارس", city="شیراز")
    assert scoring.score_pair(rf(province="فارس", city="شیراز"), pf(**onsite)).score == 100
    assert scoring.score_pair(rf(province="فارس", city="مرودشت"), pf(**onsite)).score == 60
    far = scoring.score_pair(rf(province="تهران", city="تهران"), pf(**onsite))
    assert far.score == 0 and "LOCATION_DIFFERENT_PROVINCE" in codes(far)
    remote = scoring.score_pair(rf(province="تهران"), pf(work_mode="REMOTE", province="فارس"))
    assert only(remote, "location") == {"applicable": False}


def test_salary_within_above_and_unknown():
    post = pf(salary_min=20_000_000, salary_max=40_000_000)
    assert scoring.score_pair(rf(expected_salary=30_000_000), post).score == 100
    assert scoring.score_pair(rf(expected_salary=10_000_000), post).score == 100  # asks for less
    assert scoring.score_pair(rf(expected_salary=50_000_000), post).score == 60  # ratio .8
    assert scoring.score_pair(rf(expected_salary=100_000_000), post).score == 0
    assert "SALARY_ABOVE_RANGE" in codes(scoring.score_pair(rf(expected_salary=50_000_000), post))
    assert only(scoring.score_pair(rf(), post), "salary") == {"applicable": False}
    assert not only(
        scoring.score_pair(rf(expected_salary=1), pf(post_type="PROJECT")), "salary"
    ).get("applicable")


# ------------------------------------------------------------------ combination
def test_weights_are_renormalized_over_applicable_factors():
    r = scoring.score_pair(
        rf(skills=((1, "الف", "EXPERT"),), work_modes=("ON_SITE",)),
        pf(required_skills=((1, "الف", ""),), work_mode="REMOTE"),
    )
    # skills 1.0 (w .4) and work mode 0.0 (w .1) -> .4 / .5
    assert r.score == 80


def test_weights_are_configurable(settings):
    settings.MATCHING = {
        **settings.MATCHING,
        "WEIGHTS": {**settings.MATCHING["WEIGHTS"], "skills": 0.1, "work_mode": 0.9},
    }
    r = scoring.score_pair(
        rf(skills=((1, "الف", "EXPERT"),), work_modes=("ON_SITE",)),
        pf(required_skills=((1, "الف", ""),), work_mode="REMOTE"),
    )
    assert r.score == 10


def good_resume():
    return rf(
        skills=(),
        title_terms=("جنگو",),
        experience_level="MID",
        work_modes=("ON_SITE",),
        province="تهران",
        city="تهران",
        expected_salary=10_000_000,
    )


def good_post(**kw):
    return pf(
        title="جنگو",
        title_norm="جنگو",
        required_experience="MID",
        work_mode="ON_SITE",
        province="تهران",
        city="تهران",
        salary_min=1,
        salary_max=20_000_000,
        **kw,
    )


def test_hard_constraint_caps_the_score_but_never_removes_it():
    uncapped = scoring.score_pair(good_resume(), good_post())
    capped = scoring.score_pair(good_resume(), good_post(required_skills=((9, "ناموجود", ""),)))
    assert uncapped.score > 80 and uncapped.flags == []
    assert capped.flags == ["NO_REQUIRED_SKILLS_MATCHED"] and capped.capped
    assert capped.score == scoring.config()["HARD_CONSTRAINT_CAP"] == 40
    warning = next(r for r in capped.reasons if r["code"] == "HARD_CONSTRAINT_WARNING")
    assert warning["polarity"] == "negative" and warning["params"]["flags"] == capped.flags


def test_hard_constraint_does_not_raise_a_low_score():
    r = scoring.score_pair(
        rf(skills=((1, "x", "EXPERT"),), work_modes=("REMOTE",)),
        pf(required_skills=((9, "ی", ""),), work_mode="ON_SITE"),
    )
    assert r.score < 40 and "NO_REQUIRED_SKILLS_MATCHED" in r.flags and not r.capped


def test_on_site_other_province_and_far_below_experience_are_hard_constraints():
    far = scoring.score_pair(
        rf(province="تهران", experience_level="NO_EXPERIENCE"),
        pf(work_mode="ON_SITE", province="فارس", required_experience="SENIOR"),
    )
    assert set(far.flags) == {"ON_SITE_IN_DIFFERENT_PROVINCE", "EXPERIENCE_FAR_BELOW"}


# ------------------------------------------------------------------ semantic part
def test_semantic_similarity_is_mixed_with_the_kind_weight():
    resume = rf(skills=((1, "الف", "EXPERT"), (2, "ب", "EXPERT")))
    post = pf(
        required_skills=((1, "الف", ""), (2, "ب", ""), (3, "ج", ""), (4, "د", ""))
    )  # structured 0.5
    base = scoring.score_pair(resume, post)
    assert base.score == 50 and base.semantic is None
    lexical = scoring.score_pair(
        resume, post, cosine=0.9, provider_kind="lexical"
    )  # normalized 1.0
    neural = scoring.score_pair(resume, post, cosine=0.9, provider_kind="neural")  # normalized 1.0
    assert lexical.score == round((0.8 * 0.5 + 0.2 * 1.0) * 100) == 60
    assert neural.score == round((0.65 * 0.5 + 0.35 * 1.0) * 100) == 68
    assert "SEMANTIC_SIMILAR" in codes(lexical)


def test_cosine_is_normalized_per_provider_kind():
    assert (
        scoring.normalize_similarity(0.15, "lexical") == 0
        and scoring.normalize_similarity(0.55, "lexical") == 1
    )
    assert scoring.normalize_similarity(0.35, "lexical") == pytest.approx(0.5)
    assert (
        scoring.normalize_similarity(0.30, "neural") == 0
        and scoring.normalize_similarity(0.99, "neural") == 1
    )
    assert scoring.normalize_similarity(-1, "neural") == 0


def test_missing_semantic_is_stated_not_hidden():
    unavailable = scoring.score_pair(rf(work_modes=("REMOTE",)), pf())
    pending = scoring.score_pair(
        rf(work_modes=("REMOTE",)), pf(), provider_kind="neural", semantic_pending=True
    )
    assert "SEMANTIC_UNAVAILABLE" in codes(unavailable) and unavailable.semantic is None
    assert "SEMANTIC_PENDING" in codes(pending) and pending.semantic is None


def test_nothing_to_compare_gives_zero_with_an_explanation():
    r = scoring.score_pair(rf(), pf())
    assert r.score == 0 and "INSUFFICIENT_DATA" in codes(r) and r.structured is None


def test_only_semantic_available():
    r = scoring.score_pair(rf(), pf(), cosine=0.55, provider_kind="lexical")
    assert r.score == 100 and r.structured is None


def test_scores_are_bounded_integers_and_deterministic():
    rng = random.Random(7)  # noqa: S311 - reproducible test data, not security
    modes = ["ON_SITE", "REMOTE", "HYBRID"]
    for _ in range(400):
        resume = rf(
            skills=tuple(
                (i, f"s{i}", rng.choice(["BEGINNER", "EXPERT"]))
                for i in rng.sample(range(8), rng.randint(0, 5))
            ),
            title_terms=rng.choice([(), ("جنگو",), ("حسابدار",)]),
            experience_level=rng.choice(["", "NO_EXPERIENCE", "JUNIOR", "MID", "SENIOR"]),
            highest_degree=rng.randint(-1, 5),
            work_modes=tuple(rng.sample(modes, rng.randint(0, 3))),
            province=rng.choice(["", "فارس", "تهران"]),
            city=rng.choice(["", "شیراز"]),
            expected_salary=rng.choice([None, 5, 10**9]),
        )
        post = pf(
            post_type=rng.choice(["EMPLOYMENT", "PROJECT"]),
            required_skills=tuple(
                (i, f"s{i}", rng.choice(["", "ADVANCED"]))
                for i in rng.sample(range(8), rng.randint(0, 4))
            ),
            optional_skills=tuple(
                (i, f"s{i}", "") for i in rng.sample(range(8, 12), rng.randint(0, 2))
            ),
            work_mode=rng.choice(modes),
            province=rng.choice(["", "فارس", "تهران"]),
            required_experience=rng.choice(["", "JUNIOR", "SENIOR"]),
            required_degree=rng.randint(-1, 5),
            salary_min=1,
            salary_max=rng.choice([None, 20_000_000]),
            title_norm="جنگو",
        )
        cosine = rng.choice([None, -0.5, 0.0, 0.3, 1.0])
        a = scoring.score_pair(resume, post, cosine=cosine, provider_kind="neural")
        b = scoring.score_pair(resume, post, cosine=cosine, provider_kind="neural")
        assert isinstance(a.score, int) and 0 <= a.score <= 100
        assert (a.score, a.flags, a.reasons) == (b.score, b.flags, b.reasons)
        if a.flags:
            assert a.score <= 40


def test_top_reasons_put_warnings_first_and_limit_to_three():
    reasons = [
        {"code": c, "polarity": p}
        for c, p in [
            ("A", "info"),
            ("B", "positive"),
            ("C", "negative"),
            ("D", "positive"),
            ("E", "negative"),
        ]
    ]
    assert [r["code"] for r in scoring.top_reasons(reasons)] == ["C", "E", "B"]
    with_hard = [*reasons, {"code": "HARD_CONSTRAINT_WARNING", "polarity": "negative"}]
    assert scoring.top_reasons(with_hard)[0]["code"] == "HARD_CONSTRAINT_WARNING"  # always first
    assert list(itertools.islice(scoring.top_reasons(reasons, limit=1), 5))[0]["code"] == "C"
