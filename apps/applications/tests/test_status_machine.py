"""The status machines of applications and proposals, tested with the same scenarios."""

import pytest

from apps.applications.models import (
    Application,
    ApplicationStatusHistory,
    ProjectProposal,
    ProjectProposalStatusHistory,
)

pytestmark = pytest.mark.django_db

CASES = {
    "application": {
        "base": "/api/v1/applications/",
        "model": Application,
        "history": ApplicationStatusHistory,
        "chain": ["REVIEWING", "INTERVIEW", "ACCEPTED"],
        "employer_next": {
            "PENDING": ["REJECTED", "REVIEWING"],
            "REVIEWING": ["INTERVIEW", "REJECTED"],
            "INTERVIEW": ["ACCEPTED", "REJECTED"],
        },
        "invalid_jump": ("PENDING", "ACCEPTED"),
        "active": ["PENDING", "REVIEWING", "INTERVIEW"],
    },
    "proposal": {
        "base": "/api/v1/proposals/",
        "model": ProjectProposal,
        "history": ProjectProposalStatusHistory,
        "chain": ["REVIEWING", "NEGOTIATING", "ACCEPTED"],
        "employer_next": {
            "PENDING": ["REJECTED", "REVIEWING"],
            "REVIEWING": ["ACCEPTED", "NEGOTIATING", "REJECTED"],
            "NEGOTIATING": ["ACCEPTED", "REJECTED"],
        },
        "invalid_jump": ("PENDING", "NEGOTIATING"),
        "active": ["PENDING", "REVIEWING", "NEGOTIATING"],
    },
}


@pytest.fixture(params=["application", "proposal"])
def case(request):
    return CASES[request.param]


@pytest.fixture
def scenario(request, case, make_applicant, make_application, make_proposal, job, project):
    """Returns (case, object, applicant, owner)."""
    applicant = make_applicant()
    if case is CASES["application"]:
        obj, owner = make_application(applicant), job.employer.user
    else:
        obj, owner = make_proposal(applicant), project.employer.user
    return case, obj, applicant, owner


def go(client, case, obj, status, note=None):
    body = {"status": status} if note is None else {"status": status, "note": note}
    return client.post(f"{case['base']}{obj.pk}/transition/", body, format="json")


def state(case, obj):
    return case["model"].objects.get(pk=obj.pk).status


def test_employer_walks_the_happy_path_and_every_step_is_logged(scenario, auth_client):
    case, obj, applicant, owner = scenario
    client = auth_client(owner)
    for step in case["chain"]:
        r = go(client, case, obj, step, note=f"گام {step}")
        assert r.status_code == 200 and r.json()["status"] == step
    rows = list(
        case["history"].objects.filter(
            **{("application" if "application" in case["base"] else "proposal"): obj}
        )
    )
    assert [(h.from_status, h.to_status) for h in rows] == [
        ("", "PENDING"),
        ("PENDING", case["chain"][0]),
        (case["chain"][0], case["chain"][1]),
        (case["chain"][1], case["chain"][2]),
    ]
    assert rows[-1].actor == owner and rows[-1].note == f"گام {case['chain'][2]}"
    assert rows[0].actor == applicant


def test_allowed_next_statuses_depend_on_role_and_current_status(scenario, auth_client):
    case, obj, applicant, owner = scenario
    seen_by_employer = (
        auth_client(owner).get(f"{case['base']}{obj.pk}/").json()["allowed_next_statuses"]
    )
    seen_by_applicant = (
        auth_client(applicant).get(f"{case['base']}{obj.pk}/").json()["allowed_next_statuses"]
    )
    assert seen_by_employer == sorted(case["employer_next"]["PENDING"])
    assert seen_by_applicant == ["WITHDRAWN"]


def test_invalid_jumps_are_409_and_change_nothing(scenario, auth_client):
    case, obj, _, owner = scenario
    start, target = case["invalid_jump"]
    r = go(auth_client(owner), case, obj, target)
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert "Allowed" in r.json()["error"]["message"]
    assert state(case, obj) == start
    assert case["history"].objects.count() == 1  # only the submission row


def test_cannot_go_backwards_or_repeat(scenario, auth_client):
    case, obj, _, owner = scenario
    client = auth_client(owner)
    go(client, case, obj, case["chain"][0])
    assert go(client, case, obj, case["chain"][0]).status_code == 409
    assert go(client, case, obj, "PENDING").status_code == 403  # nobody may set PENDING


@pytest.mark.parametrize("final", ["REJECTED", "ACCEPTED", "WITHDRAWN"])
def test_final_states_accept_no_more_changes(final, scenario, auth_client):
    case, obj, applicant, owner = scenario
    case["model"].objects.filter(pk=obj.pk).update(status=final)
    for who, status in ((owner, "REVIEWING"), (owner, "REJECTED"), (applicant, "WITHDRAWN")):
        assert go(auth_client(who), case, obj, status).status_code == 409
    assert state(case, obj) == final
    assert case["history"].objects.count() == 1


def test_employer_can_reject_from_every_active_state(scenario, auth_client):
    case, obj, _, owner = scenario
    for status in case["active"]:
        case["model"].objects.filter(pk=obj.pk).update(status=status)
        r = go(auth_client(owner), case, obj, "REJECTED", note="متأسفیم")
        assert r.status_code == 200 and state(case, obj) == "REJECTED"


def test_applicant_can_withdraw_from_every_active_state_only(scenario, auth_client):
    case, obj, applicant, _ = scenario
    for status in case["active"]:
        case["model"].objects.filter(pk=obj.pk).update(status=status)
        assert go(auth_client(applicant), case, obj, "WITHDRAWN").status_code == 200
        assert state(case, obj) == "WITHDRAWN"
    case["model"].objects.filter(pk=obj.pk).update(status="ACCEPTED")
    assert (
        go(auth_client(applicant), case, obj, "WITHDRAWN").status_code == 409
    )  # accepted is final


def test_applicant_can_never_set_employer_statuses(scenario, auth_client):
    case, obj, applicant, _ = scenario
    for status in ("REVIEWING", "ACCEPTED", "REJECTED", "INTERVIEW", "NEGOTIATING"):
        r = go(auth_client(applicant), case, obj, status)
        assert r.status_code in (403, 400)  # INTERVIEW/NEGOTIATING are not valid for the other kind
        assert state(case, obj) == "PENDING"


def test_employer_can_never_withdraw_on_behalf_of_the_applicant(scenario, auth_client):
    case, obj, _, owner = scenario
    assert go(auth_client(owner), case, obj, "WITHDRAWN").status_code == 403
    assert state(case, obj) == "PENDING"


def test_unknown_status_and_bad_body_are_400(scenario, auth_client):
    case, obj, _, owner = scenario
    client = auth_client(owner)
    assert go(client, case, obj, "DONE").status_code == 400
    assert client.post(f"{case['base']}{obj.pk}/transition/", {}, format="json").status_code == 400
    assert go(client, case, obj, case["chain"][0], note="x" * 1001).status_code == 400
    assert state(case, obj) == "PENDING"


def test_anonymous_and_strangers_cannot_change_status(
    scenario, api_client, auth_client, make_employer, make_applicant
):
    case, obj, _, _ = scenario
    assert go(api_client, case, obj, "REVIEWING").status_code == 401
    for stranger in (make_employer(), make_applicant()):
        assert go(auth_client(stranger), case, obj, "REVIEWING").status_code == 404
    assert state(case, obj) == "PENDING"


def test_history_endpoint_shows_roles_notes_and_order(scenario, auth_client):
    case, obj, applicant, owner = scenario
    go(auth_client(owner), case, obj, case["chain"][0], note="در حال بررسی رزومه")
    go(auth_client(applicant), case, obj, "WITHDRAWN")
    for viewer in (owner, applicant):
        rows = auth_client(viewer).get(f"{case['base']}{obj.pk}/history/").json()
        assert [(r["from_status"], r["to_status"], r["by"]) for r in rows] == [
            ("", "PENDING", "applicant"),
            ("PENDING", case["chain"][0], "employer"),
            (case["chain"][0], "WITHDRAWN", "applicant"),
        ]
        assert rows[1]["note"] == "در حال بررسی رزومه"
        assert not any("@" in str(r) for r in rows)  # roles, never emails


def test_history_rows_cannot_be_edited_in_django_admin(case):
    from django.contrib import admin as dj_admin

    for model in (ApplicationStatusHistory, ProjectProposalStatusHistory):
        ma = dj_admin.site._registry[model]
        assert not (
            ma.has_add_permission(None)
            or ma.has_change_permission(None)
            or ma.has_delete_permission(None)
        )
    assert case


def test_concurrent_looking_double_review_logs_once(scenario, auth_client):
    case, obj, _, owner = scenario
    client = auth_client(owner)
    assert go(client, case, obj, "REJECTED").status_code == 200
    assert go(client, case, obj, "REJECTED").status_code == 409
    assert case["history"].objects.filter(to_status="REJECTED").count() == 1
