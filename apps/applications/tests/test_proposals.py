import pytest

from apps.applications.models import ProjectProposal, ProjectProposalStatusHistory
from apps.applications.tests.conftest import PROPOSAL_BODY

pytestmark = pytest.mark.django_db


def propose_url(pk):
    return f"/api/v1/jobs/{pk}/proposals/"


def prop_url(pk, tail=""):
    return f"/api/v1/proposals/{pk}/{tail}"


def test_proposal_requires_login_and_job_seeker_profile(
    api_client, project, make_employer, make_user, auth_client
):
    assert api_client.post(propose_url(project.pk), PROPOSAL_BODY, format="json").status_code == 401
    assert (
        auth_client(make_employer())
        .post(propose_url(project.pk), PROPOSAL_BODY, format="json")
        .status_code
        == 403
    )
    assert (
        auth_client(make_user())
        .post(propose_url(project.pk), PROPOSAL_BODY, format="json")
        .status_code
        == 403
    )


def test_proposal_needs_no_complete_resume(project, make_seeker, auth_client):
    r = auth_client(make_seeker()).post(propose_url(project.pk), PROPOSAL_BODY, format="json")
    assert r.status_code == 201


def test_create_proposal(project, make_applicant, auth_client):
    user = make_applicant()
    r = auth_client(user).post(propose_url(project.pk), PROPOSAL_BODY, format="json")
    assert r.status_code == 201
    body = r.json()
    assert (
        body["status"] == "PENDING"
        and body["proposed_price"] == 8_000_000
        and body["estimated_days"] == 10
    )
    assert body["currency"] == "IRR" and body["contact"] is None
    assert body["allowed_next_statuses"] == ["WITHDRAWN"]
    entry = ProjectProposalStatusHistory.objects.get()
    assert (entry.from_status, entry.to_status, entry.actor) == ("", "PENDING", user)


def test_cannot_send_a_proposal_to_an_employment_post(job, make_applicant, auth_client):
    r = auth_client(make_applicant()).post(propose_url(job.pk), PROPOSAL_BODY, format="json")
    assert (
        r.status_code == 400
        and "application" in str(r.json()["error"]["details"]["detail"]).lower()
    )
    assert ProjectProposal.objects.count() == 0


@pytest.mark.parametrize("name", ["draft", "pending", "deactivated", "expired"])
def test_cannot_propose_on_hidden_posts(name, hidden_posts, make_applicant, auth_client):
    r = auth_client(make_applicant()).post(
        propose_url(hidden_posts[name].pk), PROPOSAL_BODY, format="json"
    )
    assert r.status_code == 404 and ProjectProposal.objects.count() == 0


@pytest.mark.parametrize(
    "bad",
    [
        {"proposed_price": 0},
        {"proposed_price": -100},
        {"proposed_price": "abc"},
        {"estimated_days": 0},
        {"estimated_days": -3},
        {"estimated_days": 99999},
        {"description": "too short"},
        {"description": "x" * 3001},
        {"proposed_price": None},
    ],
)
def test_proposal_validation(bad, project, make_applicant, auth_client):
    r = auth_client(make_applicant()).post(
        propose_url(project.pk), {**PROPOSAL_BODY, **bad}, format="json"
    )
    assert r.status_code == 400 and ProjectProposal.objects.count() == 0


@pytest.mark.parametrize("missing", ["proposed_price", "estimated_days", "description"])
def test_all_proposal_fields_are_required(missing, project, make_applicant, auth_client):
    body = {k: v for k, v in PROPOSAL_BODY.items() if k != missing}
    assert (
        auth_client(make_applicant()).post(propose_url(project.pk), body, format="json").status_code
        == 400
    )


def test_proposal_may_be_outside_the_budget_range(project, make_applicant, auth_client):
    r = auth_client(make_applicant()).post(
        propose_url(project.pk), {**PROPOSAL_BODY, "proposed_price": 999_999_999}, format="json"
    )
    assert r.status_code == 201  # negotiation is the employer's call


def test_cannot_propose_on_your_own_project(make_applicant, make_post, auth_client):
    from apps.jobs.models import PostType
    from apps.profiles.models import EmployerProfile

    user = make_applicant()
    EmployerProfile.objects.create(user=user, display_name="Me")
    own = make_post(employer=user, post_type=PostType.PROJECT, published=True)
    assert (
        auth_client(user).post(propose_url(own.pk), PROPOSAL_BODY, format="json").status_code == 400
    )


def test_server_controlled_fields_are_ignored(project, make_applicant, auth_client):
    victim, attacker = make_applicant(), make_applicant()
    r = auth_client(attacker).post(
        propose_url(project.pk),
        {
            **PROPOSAL_BODY,
            "status": "ACCEPTED",
            "job_seeker": victim.job_seeker_profile.pk,
            "post_type": "EMPLOYMENT",
        },
        format="json",
    )
    assert r.status_code == 201
    obj = ProjectProposal.objects.get()
    assert (
        obj.status == "PENDING"
        and obj.job_seeker == attacker.job_seeker_profile
        and obj.post_type == "PROJECT"
    )


def test_duplicate_active_proposal_is_409_but_allowed_after_withdrawal(
    project, make_applicant, auth_client, make_proposal
):
    user = make_applicant()
    first = make_proposal(user)
    client = auth_client(user)
    assert client.post(propose_url(project.pk), PROPOSAL_BODY, format="json").status_code == 409
    client.post(prop_url(first.pk, "transition/"), {"status": "WITHDRAWN"}, format="json")
    again = client.post(
        propose_url(project.pk), {**PROPOSAL_BODY, "proposed_price": 7_000_000}, format="json"
    )
    assert (
        again.status_code == 201 and ProjectProposal.objects.filter(job_post=project).count() == 2
    )


def test_a_rejected_proposal_is_not_replaceable(
    project, make_applicant, auth_client, make_proposal
):
    user = make_applicant()
    proposal = make_proposal(user)
    ProjectProposal.objects.filter(pk=proposal.pk).update(status="REJECTED")
    assert (
        auth_client(user).post(propose_url(project.pk), PROPOSAL_BODY, format="json").status_code
        == 409
    )


def test_my_proposals_and_owner_list_are_scoped(
    project, make_post, make_applicant, make_employer, make_seeker, auth_client, make_proposal
):
    from apps.jobs.models import PostType

    me, other = make_applicant(), make_applicant()
    mine = make_proposal(me)
    make_proposal(other)
    elsewhere = make_post(post_type=PostType.PROJECT, published=True)
    make_proposal(me, elsewhere)

    assert auth_client(me).get("/api/v1/proposals/mine/").json()["count"] == 2
    assert (
        auth_client(me).get("/api/v1/proposals/mine/", {"status": "PENDING"}).json()["count"] == 2
    )
    assert auth_client(me).get("/api/v1/proposals/mine/", {"status": "NOPE"}).status_code == 400

    owner = auth_client(project.employer.user)
    data = owner.get(propose_url(project.pk)).json()
    assert data["count"] == 2 and {row["id"] for row in data["results"]} >= {mine.pk}
    assert auth_client(make_employer()).get(propose_url(project.pk)).status_code == 404
    assert auth_client(make_seeker()).get(propose_url(project.pk)).status_code == 403
    assert auth_client(me).get(propose_url(project.pk)).status_code == 403
    assert auth_client(project.employer.user).get(propose_url(elsewhere.pk)).status_code == 404


def test_owner_asking_for_proposals_of_an_employment_post_is_told_to_use_applications(
    job, auth_client
):
    r = auth_client(job.employer.user).get(propose_url(job.pk))
    assert r.status_code == 400 and "applications" in str(r.json()["error"]["details"]).lower()


def test_detail_visible_only_to_the_two_parties(
    project, make_applicant, make_employer, make_seeker, api_client, auth_client, make_proposal
):
    applicant = make_applicant()
    proposal = make_proposal(applicant)
    assert api_client.get(prop_url(proposal.pk)).status_code == 401
    for allowed in (applicant, project.employer.user):
        assert auth_client(allowed).get(prop_url(proposal.pk)).status_code == 200
    for stranger in (make_applicant(), make_seeker(), make_employer()):
        client = auth_client(stranger)
        assert client.get(prop_url(proposal.pk)).status_code == 404
        assert client.get(prop_url(proposal.pk, "history/")).status_code == 404
        assert (
            client.post(
                prop_url(proposal.pk, "transition/"), {"status": "REVIEWING"}, format="json"
            ).status_code
            == 404
        )


def test_contact_details_are_released_only_on_acceptance_and_only_to_the_employer(
    project, make_applicant, auth_client, make_proposal
):
    applicant = make_applicant(email="freelancer@example.com", phone="09127776655")
    proposal = make_proposal(applicant)
    owner, seeker = auth_client(project.employer.user), auth_client(applicant)
    for step in ("REVIEWING", "NEGOTIATING"):
        body = owner.post(
            prop_url(proposal.pk, "transition/"), {"status": step}, format="json"
        ).json()
        assert body["contact"] is None
    assert "freelancer@example.com" not in str(owner.get(propose_url(project.pk)).json())
    accepted = owner.post(
        prop_url(proposal.pk, "transition/"), {"status": "ACCEPTED"}, format="json"
    ).json()
    assert accepted["contact"] == {"email": "freelancer@example.com", "phone": "09127776655"}
    assert (
        owner.get(propose_url(project.pk)).json()["results"][0]["contact"]["email"]
        == "freelancer@example.com"
    )
    assert (
        seeker.get(prop_url(proposal.pk)).json()["contact"] is None
    )  # not echoed back to the seeker


def test_proposals_list_query_count(
    project, make_applicant, auth_client, make_proposal, django_assert_max_num_queries
):
    for _ in range(12):
        make_proposal(make_applicant())
    with django_assert_max_num_queries(6):
        r = auth_client(project.employer.user).get(propose_url(project.pk), {"page_size": 12})
    assert len(r.json()["results"]) == 12
