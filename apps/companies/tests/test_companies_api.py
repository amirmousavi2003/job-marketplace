import pytest
from django.db import IntegrityError, transaction

from apps.companies.models import Company, CompanyMembership
from apps.companies.services import create_company

pytestmark = pytest.mark.django_db

LIST = "/api/v1/companies/"


def detail(pk):
    return f"/api/v1/companies/{pk}/"


def members(pk):
    return f"/api/v1/companies/{pk}/members/"


def test_requires_employer_profile(make_seeker, make_user, auth_client):
    assert auth_client(make_seeker()).post(LIST, {"name": "X"}, format="json").status_code == 403
    assert auth_client(make_user()).get(LIST).status_code == 403


def test_anonymous_is_401(api_client):
    assert api_client.get(LIST).status_code == 401


def test_create_makes_creator_owner(make_employer, auth_client):
    user = make_employer()
    r = auth_client(user).post(
        LIST, {"name": "Acme", "is_verified": True, "website": "https://acme.ir"}, format="json"
    )
    assert r.status_code == 201
    assert r.json()["my_role"] == "OWNER"
    assert r.json()["is_verified"] is False  # cannot self-verify
    assert Company.objects.get().is_verified is False


def test_list_shows_only_my_companies_with_correct_role(make_employer, auth_client):
    me, other = make_employer(), make_employer()
    mine = create_company(employer=me.employer_profile, name="Mine")
    theirs = create_company(employer=other.employer_profile, name="Theirs")
    CompanyMembership.objects.create(company=theirs, employer=me.employer_profile)

    data = auth_client(me).get(LIST).json()
    roles = {c["name"]: c["my_role"] for c in data["results"]}
    assert roles == {"Mine": "OWNER", "Theirs": "MEMBER"}
    assert data["count"] == 2
    assert mine.pk


def test_non_member_gets_404_not_403(make_employer, auth_client):
    owner, stranger = make_employer(), make_employer()
    company = create_company(employer=owner.employer_profile, name="Secret")
    client = auth_client(stranger)
    assert client.get(detail(company.pk)).status_code == 404
    assert client.patch(detail(company.pk), {"name": "Hacked"}, format="json").status_code == 404
    assert client.delete(detail(company.pk)).status_code == 404
    assert client.get(members(company.pk)).status_code == 404


def test_owner_can_update_member_cannot(make_employer, auth_client):
    owner, member = make_employer(), make_employer()
    company = create_company(employer=owner.employer_profile, name="Acme")
    CompanyMembership.objects.create(company=company, employer=member.employer_profile)

    assert (
        auth_client(owner).patch(detail(company.pk), {"name": "Acme 2"}, format="json").status_code
        == 200
    )
    r = auth_client(member).patch(detail(company.pk), {"name": "Nope"}, format="json")
    assert r.status_code == 403
    assert auth_client(member).get(detail(company.pk)).status_code == 200
    company.refresh_from_db()
    assert company.name == "Acme 2"


def test_delete_deactivates_and_hides(make_employer, auth_client):
    owner = make_employer()
    company = create_company(employer=owner.employer_profile, name="Acme")
    client = auth_client(owner)
    assert client.delete(detail(company.pk)).status_code == 204
    company.refresh_from_db()
    assert company.is_active is False  # soft delete
    assert client.get(detail(company.pk)).status_code == 404
    assert client.get(LIST).json()["count"] == 0


def test_owner_adds_member_by_email(make_employer, make_user, auth_client):
    owner, colleague = make_employer(), make_employer(email="col@example.com")
    company = create_company(employer=owner.employer_profile, name="Acme")
    client = auth_client(owner)

    r = client.post(members(company.pk), {"email": "COL@example.com"}, format="json")
    assert r.status_code == 201 and r.json()["role"] == "MEMBER"
    assert (
        client.post(members(company.pk), {"email": "col@example.com"}, format="json").status_code
        == 400
    )
    assert (
        client.post(members(company.pk), {"email": "ghost@example.com"}, format="json").status_code
        == 400
    )
    make_user("plain@example.com")  # exists but has no employer profile
    assert (
        client.post(members(company.pk), {"email": "plain@example.com"}, format="json").status_code
        == 400
    )
    assert client.get(members(company.pk)).json()["count"] == 2
    assert colleague.employer_profile.company_memberships.count() == 1


def test_member_cannot_add_members(make_employer, auth_client):
    owner, member, third = make_employer(), make_employer(), make_employer(email="t@example.com")
    company = create_company(employer=owner.employer_profile, name="Acme")
    CompanyMembership.objects.create(company=company, employer=member.employer_profile)
    r = auth_client(member).post(members(company.pk), {"email": "t@example.com"}, format="json")
    assert r.status_code == 403
    assert third.employer_profile.company_memberships.count() == 0


def test_remove_member_rules(make_employer, auth_client):
    owner, m1, m2 = make_employer(), make_employer(), make_employer()
    company = create_company(employer=owner.employer_profile, name="Acme")
    mem1 = CompanyMembership.objects.create(company=company, employer=m1.employer_profile)
    mem2 = CompanyMembership.objects.create(company=company, employer=m2.employer_profile)
    owner_mem = CompanyMembership.objects.get(company=company, role="OWNER")

    def url(m):
        return f"/api/v1/companies/{company.pk}/members/{m.pk}/"

    assert auth_client(m1).delete(url(mem2)).status_code == 403  # member removing someone else
    assert auth_client(owner).delete(url(owner_mem)).status_code == 400  # owner is permanent
    assert auth_client(m1).delete(url(mem1)).status_code == 204  # member leaves
    assert auth_client(owner).delete(url(mem2)).status_code == 204  # owner removes member
    assert CompanyMembership.objects.filter(company=company).count() == 1


def test_member_id_from_another_company_is_404(make_employer, auth_client):
    a, b = make_employer(), make_employer()
    ca = create_company(employer=a.employer_profile, name="A")
    cb = create_company(employer=b.employer_profile, name="B")
    foreign = CompanyMembership.objects.get(company=cb)
    r = auth_client(a).delete(f"/api/v1/companies/{ca.pk}/members/{foreign.pk}/")
    assert r.status_code == 404
    assert CompanyMembership.objects.filter(pk=foreign.pk).exists()


def test_db_allows_only_one_owner_per_company(make_employer):
    owner, other = make_employer(), make_employer()
    company = create_company(employer=owner.employer_profile, name="Acme")
    with pytest.raises(IntegrityError), transaction.atomic():
        CompanyMembership.objects.create(
            company=company, employer=other.employer_profile, role="OWNER"
        )


def test_db_rejects_duplicate_membership(make_employer):
    owner = make_employer()
    company = create_company(employer=owner.employer_profile, name="Acme")
    with pytest.raises(IntegrityError), transaction.atomic():
        CompanyMembership.objects.create(company=company, employer=owner.employer_profile)
