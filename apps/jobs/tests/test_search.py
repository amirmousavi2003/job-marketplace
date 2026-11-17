import datetime

import pytest
from django.utils import timezone

from apps.companies.services import create_company
from apps.jobs.models import JobPost, PostType
from apps.locations.models import Province
from apps.skills.models import JobCategory

pytestmark = pytest.mark.django_db

LIST = "/api/v1/jobs/"


@pytest.fixture
def data(make_post, make_skill, category, shiraz, staff):
    django, react, photoshop = (
        make_skill("Django", "جنگو"),
        make_skill("React", "ری‌اکت"),
        make_skill("Photoshop", "فتوشاپ"),
    )
    finance = JobCategory.objects.get(slug="finance")
    design = JobCategory.objects.get(slug="design")
    backend = JobCategory.objects.create(name_fa="توسعه بک‌اند", slug="backend", parent=category)
    tehran = Province.objects.get(name="تهران")

    def emp(**d):
        return {
            "employment_type": "FULL_TIME",
            "salary_min": 20_000_000,
            "salary_max": 40_000_000,
            **d,
        }

    a = make_post(
        title="برنامه‌نویس جنگو",
        published=True,
        skills=[django],
        detail=emp(required_experience_level="MID"),
    )
    b = make_post(
        title="حسابدار ارشد",
        published=True,
        category=finance,
        work_mode="ON_SITE",
        province=shiraz.province,
        city=shiraz,
        detail=emp(
            employment_type="PART_TIME",
            salary_min=10_000_000,
            salary_max=15_000_000,
            required_experience_level="SENIOR",
        ),
    )
    c = make_post(
        title="طراحی لوگو",
        post_type=PostType.PROJECT,
        published=True,
        category=design,
        skills=[photoshop],
        detail={"budget_min": 5_000_000, "budget_max": 10_000_000, "currency": "IRR"},
    )
    d = make_post(
        title="توسعه سایت با ری‌اکت",
        description="نیاز به آشنایی با جنگو برای ساخت API هم هست.",
        post_type=PostType.PROJECT,
        published=True,
        category=backend,
        work_mode="HYBRID",
        province=tehran,
        skills=[react, django],
        detail={"budget_min": 30_000_000, "budget_max": 60_000_000, "currency": "IRR"},
    )
    draft = make_post(title="پیش‌نویس جنگو محرمانه", skills=[django])
    return {
        "a": a,
        "b": b,
        "c": c,
        "d": d,
        "draft": draft,
        "django": django,
        "react": react,
        "category": category,
        "backend": backend,
        "design": design,
        "shiraz": shiraz,
        "tehran": tehran,
    }


def ids(client, params=None, path=LIST):
    r = client.get(path, params or {})
    assert r.status_code == 200, r.json()
    return [row["id"] for row in r.json()["results"]]


# ------------------------------------------------------------------ keyword
def test_keyword_matches_title_and_description_and_ranks_title_first(api_client, data):
    assert ids(api_client, {"q": "جنگو"}) == [
        data["a"].pk,
        data["d"].pk,
    ]  # title match before description match


def test_keyword_ignores_unpublished_posts(api_client, data):
    assert data["draft"].pk not in ids(api_client, {"q": "جنگو"})
    assert ids(api_client, {"q": "محرمانه"}) == []


def test_keyword_is_normalization_tolerant(api_client, data):
    assert ids(api_client, {"q": "ری اکت"}) == [data["d"].pk]  # space instead of ZWNJ
    assert ids(api_client, {"q": "  ری‌اکت  "}) == [data["d"].pk]
    assert ids(api_client, {"q": "حسابدار"}) == [data["b"].pk]


def test_keyword_arabic_letters_find_persian_text(api_client, make_post):
    post = make_post(title="کارشناس کیبورد", published=True)
    assert ids(api_client, {"q": "كيبورد"}) == [post.pk]  # Arabic kaf/yeh


def test_keyword_tokens_are_anded_and_search_location_skills_company(
    api_client, data, make_employer, make_post
):
    assert ids(api_client, {"q": "حسابدار شیراز"}) == [data["b"].pk]  # city name is searchable
    assert ids(api_client, {"q": "حسابدار تهران"}) == []
    assert data["c"].pk in ids(api_client, {"q": "فتوشاپ"})  # skill name is searchable
    owner = make_employer()
    company = create_company(employer=owner.employer_profile, name="شرکت آسمان‌پرداز")
    post = make_post(employer=owner, company=company, published=True)
    assert ids(api_client, {"q": "آسمان پرداز"}) == [post.pk]


def test_keyword_wildcards_are_literal(api_client, data):
    for q in ("%", "_", "%جنگو%", "جن_و"):
        assert ids(api_client, {"q": q}) == []


def test_blank_keyword_returns_everything_public(api_client, data):
    assert set(ids(api_client, {"q": "   "})) == {data[k].pk for k in "abcd"}


# ------------------------------------------------------------------ simple filters
def test_category_filter_includes_subcategories(api_client, data):
    assert set(ids(api_client, {"category": data["category"].pk})) == {data["a"].pk, data["d"].pk}
    assert ids(api_client, {"category": data["backend"].pk}) == [data["d"].pk]
    assert ids(api_client, {"category": data["design"].pk}) == [data["c"].pk]


def test_type_filter_and_typed_endpoints(api_client, data):
    assert set(ids(api_client, {"type": "EMPLOYMENT"})) == {data["a"].pk, data["b"].pk}
    assert set(ids(api_client, {"type": "PROJECT"})) == {data["c"].pk, data["d"].pk}
    assert set(ids(api_client, path="/api/v1/jobs/employment/")) == {data["a"].pk, data["b"].pk}
    assert set(ids(api_client, path="/api/v1/jobs/projects/")) == {data["c"].pk, data["d"].pk}


def test_location_and_work_mode_filters(api_client, data):
    assert ids(api_client, {"city": data["shiraz"].pk}) == [data["b"].pk]
    assert ids(api_client, {"province": data["shiraz"].province_id}) == [data["b"].pk]
    assert ids(api_client, {"province": data["tehran"].pk}) == [data["d"].pk]
    assert set(ids(api_client, {"work_mode": "REMOTE"})) == {data["a"].pk, data["c"].pk}
    assert ids(api_client, {"work_mode": "HYBRID"}) == [data["d"].pk]


def test_employment_specific_filters_exclude_projects(api_client, data):
    assert ids(api_client, {"employment_type": "PART_TIME"}) == [data["b"].pk]
    assert ids(api_client, {"employment_type": "FULL_TIME"}) == [data["a"].pk]
    assert ids(api_client, {"experience_level": "SENIOR"}) == [data["b"].pk]
    assert ids(api_client, {"experience_level": "MID"}) == [data["a"].pk]


# ------------------------------------------------------------------ ranges (overlap semantics)
def test_salary_range_overlap(api_client, data):
    assert ids(api_client, {"salary_min": 30_000_000}) == [data["a"].pk]  # pays up to >= 30M
    assert ids(api_client, {"salary_max": 12_000_000}) == [data["b"].pk]  # starts at or below 12M
    assert ids(api_client, {"salary_min": 12_000_000, "salary_max": 18_000_000}) == [data["b"].pk]
    assert set(ids(api_client, {"salary_min": 1})) == {
        data["a"].pk,
        data["b"].pk,
    }  # projects excluded
    assert ids(api_client, {"salary_min": 900_000_000}) == []


def test_budget_range_overlap(api_client, data):
    assert ids(api_client, {"budget_min": 20_000_000}) == [data["d"].pk]
    assert ids(api_client, {"budget_max": 6_000_000}) == [data["c"].pk]
    assert set(ids(api_client, {"budget_min": 8_000_000, "budget_max": 35_000_000})) == {
        data["c"].pk,
        data["d"].pk,
    }


# ------------------------------------------------------------------ skills
def test_skills_any_and_all(api_client, data):
    dj, rc = data["django"].pk, data["react"].pk
    assert set(ids(api_client, {"skills": str(dj)})) == {data["a"].pk, data["d"].pk}
    assert set(ids(api_client, {"skills": f"{dj},{rc}"})) == {data["a"].pk, data["d"].pk}
    assert ids(api_client, {"skills": f"{dj},{rc}", "skills_match": "all"}) == [data["d"].pk]


def test_skills_filter_rejects_garbage(api_client, data):
    assert api_client.get(LIST, {"skills": "a,b"}).status_code == 400
    assert (
        api_client.get(LIST, {"skills": ",".join(str(i) for i in range(1, 30))}).status_code == 400
    )
    assert api_client.get(LIST, {"skills": "1", "skills_match": "most"}).status_code == 400


# ------------------------------------------------------------------ dates, ordering, paging
def test_published_after(api_client, data):
    JobPost.objects.filter(pk=data["b"].pk).update(
        published_at=timezone.now() - datetime.timedelta(days=10)
    )
    cutoff = (timezone.localdate() - datetime.timedelta(days=5)).isoformat()
    assert data["b"].pk not in ids(api_client, {"published_after": cutoff})
    assert {data["a"].pk, data["c"].pk, data["d"].pk} <= set(
        ids(api_client, {"published_after": cutoff})
    )
    assert api_client.get(LIST, {"published_after": "not-a-date"}).status_code == 400


def test_default_order_is_newest_first_and_ordering_param(api_client, data):
    now = timezone.now()
    for offset, key in enumerate("abcd"):
        JobPost.objects.filter(pk=data[key].pk).update(
            published_at=now - datetime.timedelta(days=offset)
        )
    assert ids(api_client) == [data[k].pk for k in "abcd"]
    assert ids(api_client, {"ordering": "published_at"}) == [data[k].pk for k in "dcba"]
    assert api_client.get(LIST, {"ordering": "title"}).status_code == 400
    assert api_client.get(LIST, {"ordering": "password"}).status_code == 400


def test_pagination_shape_size_and_no_overlap(api_client, make_post):
    for _ in range(7):
        make_post(published=True)
    first = api_client.get(LIST, {"page_size": 3}).json()
    assert (
        set(first) == {"count", "next", "previous", "results"}
        and first["count"] == 7
        and len(first["results"]) == 3
    )
    second = api_client.get(LIST, {"page_size": 3, "page": 2}).json()
    assert {r["id"] for r in first["results"]}.isdisjoint({r["id"] for r in second["results"]})
    assert len(api_client.get(LIST, {"page_size": 500}).json()["results"]) == 7  # capped at 50


def test_invalid_filter_values_are_400_not_500(api_client, data):
    for params in (
        {"work_mode": "BOGUS"},
        {"type": "X"},
        {"province": "abc"},
        {"salary_min": "x"},
        {"employment_type": "N"},
        {"experience_level": "GOD"},
        {"category": "x"},
    ):
        assert api_client.get(LIST, params).status_code == 400


def test_filters_combine_with_and(api_client, data):
    assert ids(api_client, {"q": "جنگو", "type": "PROJECT"}) == [data["d"].pk]
    assert ids(api_client, {"work_mode": "REMOTE", "type": "PROJECT"}) == [data["c"].pk]
    assert ids(api_client, {"work_mode": "HYBRID", "type": "EMPLOYMENT"}) == []


def test_list_query_count_does_not_grow_with_posts(
    api_client, make_post, make_skill, django_assert_max_num_queries
):
    skills = [make_skill(f"Skill {i}") for i in range(3)]
    for _ in range(12):
        make_post(published=True, skills=skills)
    with django_assert_max_num_queries(6):
        r = api_client.get(LIST, {"page_size": 12})
    assert len(r.json()["results"]) == 12 and len(r.json()["results"][0]["skills"]) == 3


def test_detail_query_count_is_bounded(
    api_client, make_post, make_skill, django_assert_max_num_queries
):
    post = make_post(published=True, skills=[make_skill(f"S{i}") for i in range(5)])
    with django_assert_max_num_queries(6):
        assert api_client.get(f"/api/v1/jobs/{post.pk}/").status_code == 200
