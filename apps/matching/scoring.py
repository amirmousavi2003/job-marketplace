"""Steps 5-8 of the pipeline: structured compatibility, hard constraints, combination, explanation.

Pure functions: no database, no network. The score is a rough, explainable compatibility
indicator. It is assistive only: nothing here accepts, rejects or ranks anyone out."""

from dataclasses import dataclass, field

from django.conf import settings

from .features import EXPERIENCE_RANK, SKILL_RANK, PostFeatures, ResumeFeatures

SCORING_VERSION = "1"


@dataclass
class MatchResult:
    score: int
    structured: float | None
    semantic: float | None  # normalized 0..1, None when unavailable
    factors: dict
    reasons: list
    flags: list = field(default_factory=list)
    capped: bool = False


def config() -> dict:
    return settings.MATCHING


def _reason(code, polarity, text_fa, **params):
    return {"code": code, "polarity": polarity, "params": params, "text_fa": text_fa}


# ------------------------------------------------------------------ factors
def _skills(resume: ResumeFeatures, post: PostFeatures):
    mine = {sid: level for sid, _, level in resume.skills}
    required, optional = post.required_skills, post.optional_skills
    if not required and not optional:
        return None

    def coverage(rows):
        credit, missing = 0.0, []
        for sid, label, min_level in rows:
            if sid not in mine:
                missing.append(label)
            elif min_level and SKILL_RANK.get(mine[sid], 0) < SKILL_RANK.get(min_level, 0):
                credit += 0.5  # has the skill, below the requested level
            else:
                credit += 1.0
        return (credit / len(rows) if rows else None), missing

    req_cov, missing_required = coverage(required)
    opt_cov, _ = coverage(optional)
    if req_cov is not None and opt_cov is not None:
        value = 0.8 * req_cov + 0.2 * opt_cov
    else:
        value = req_cov if req_cov is not None else opt_cov
    matched_required = [label for sid, label, _ in required if sid in mine]
    return {
        "value": value,
        "details": {
            "required_total": len(required),
            "required_matched": len(matched_required),
            "optional_total": len(optional),
            "optional_matched": sum(1 for sid, _, _ in optional if sid in mine),
            "missing_required": missing_required,
        },
    }


def _title(resume: ResumeFeatures, post: PostFeatures):
    if not resume.title_terms:
        return None
    post_tokens = set(post.title_norm.split())
    best = 0.0
    for term in resume.title_terms:
        if term and (term in post.title_norm or post.title_norm in term):
            best = 1.0
            break
        tokens = set(term.split())
        if tokens:
            best = max(best, len(tokens & post_tokens) / len(tokens))
    return {"value": best, "details": {}}


def _experience(resume, post):
    if (
        post.post_type != "EMPLOYMENT"
        or not post.required_experience
        or not resume.experience_level
    ):
        return None
    gap = EXPERIENCE_RANK[resume.experience_level] - EXPERIENCE_RANK[post.required_experience]
    return {"value": 1.0 if gap >= 0 else 0.5 if gap == -1 else 0.0, "details": {"gap": gap}}


def _education(resume, post):
    if post.post_type != "EMPLOYMENT" or post.required_degree < 0:
        return None
    if resume.highest_degree < 0:
        return {"value": None, "details": {"not_provided": True}}  # unknown, not penalized
    gap = resume.highest_degree - post.required_degree
    return {"value": 1.0 if gap >= 0 else 0.5 if gap == -1 else 0.0, "details": {"gap": gap}}


def _work_mode(resume, post):
    if not resume.work_modes:
        return None
    if post.work_mode in resume.work_modes:
        return {"value": 1.0, "details": {}}
    if post.work_mode == "HYBRID":  # hybrid is partly remote and partly on-site
        return {"value": 0.5, "details": {"partial": True}}
    return {"value": 0.0, "details": {}}


def _location(resume, post):
    if post.work_mode == "REMOTE" or not post.province or not resume.province:
        return None
    if post.city and resume.city and post.city == resume.city:
        return {"value": 1.0, "details": {"level": "city"}}
    if post.province == resume.province:
        return {"value": 0.6 if post.city else 1.0, "details": {"level": "province"}}
    return {"value": 0.0, "details": {"level": "different"}}


def _salary(resume, post):
    if post.post_type != "EMPLOYMENT" or not resume.expected_salary or not post.salary_max:
        return None
    if resume.expected_salary <= post.salary_max:
        return {"value": 1.0, "details": {"within": True}}
    ratio = post.salary_max / resume.expected_salary
    return {"value": max(0.0, (ratio - 0.5) * 2), "details": {"within": False}}


FACTOR_FUNCTIONS = {
    "skills": _skills,
    "title": _title,
    "experience": _experience,
    "education": _education,
    "work_mode": _work_mode,
    "location": _location,
    "salary": _salary,
}


# ------------------------------------------------------------------ explanations
def _explain(name, factor, resume, post) -> list:
    value, d = factor["value"], factor["details"]
    if name == "skills":
        out = []
        total = d["required_total"] + d["optional_total"]
        matched = d["required_matched"] + d["optional_matched"]
        if value >= 0.8:
            out.append(
                _reason(
                    "SKILL_OVERLAP_STRONG",
                    "positive",
                    "هم‌پوشانی قوی مهارت‌ها",
                    matched=matched,
                    total=total,
                )
            )
        elif value >= 0.4:
            out.append(
                _reason(
                    "SKILL_OVERLAP_PARTIAL",
                    "info",
                    "بخشی از مهارت‌های مورد نیاز را دارید",
                    matched=matched,
                    total=total,
                )
            )
        elif value > 0:
            out.append(
                _reason(
                    "SKILL_OVERLAP_WEAK",
                    "negative",
                    "هم‌پوشانی مهارت‌ها کم است",
                    matched=matched,
                    total=total,
                )
            )
        else:
            out.append(
                _reason("SKILL_OVERLAP_NONE", "negative", "هیچ‌کدام از مهارت‌های آگهی در رزومه نیست")
            )
        if d["missing_required"]:
            out.append(
                _reason(
                    "MISSING_REQUIRED_SKILLS",
                    "negative",
                    "مهارت‌های لازم که در رزومه نیست: " + "، ".join(d["missing_required"]),
                    skills=d["missing_required"],
                )
            )
        return out
    if name == "title":
        if value >= 0.99:
            return [
                _reason(
                    "TITLE_MATCH", "positive", "عنوان آگهی با عنوان شغلی مورد علاقه شما یکی است"
                )
            ]
        if value >= 0.5:
            return [
                _reason(
                    "TITLE_PARTIAL_MATCH",
                    "info",
                    "عنوان آگهی تا حدی با عنوان شغلی مورد علاقه شما مرتبط است",
                )
            ]
        return []
    if name == "experience":
        if value == 1.0:
            return [
                _reason("EXPERIENCE_MEETS", "positive", "سطح تجربه شما با نیاز آگهی سازگار است")
            ]
        if value == 0.5:
            return [
                _reason(
                    "EXPERIENCE_ONE_LEVEL_BELOW",
                    "negative",
                    "سطح تجربه شما یک پله پایین‌تر از نیاز آگهی است",
                )
            ]
        return [_reason("EXPERIENCE_FAR_BELOW", "negative", "سطح تجربه شما کمتر از نیاز آگهی است")]
    if name == "education":
        if d.get("not_provided"):
            return [
                _reason(
                    "EDUCATION_NOT_PROVIDED",
                    "info",
                    "تحصیلات در رزومه ثبت نشده و در امتیاز لحاظ نشد",
                )
            ]
        if value == 1.0:
            return [_reason("EDUCATION_MEETS", "positive", "مدرک تحصیلی با نیاز آگهی سازگار است")]
        return [_reason("EDUCATION_BELOW", "negative", "مدرک تحصیلی پایین‌تر از نیاز آگهی است")]
    if name == "work_mode":
        if value == 1.0:
            return [_reason("WORK_MODE_COMPATIBLE", "positive", "شیوه کار با ترجیح شما سازگار است")]
        if value == 0.5:
            return [
                _reason(
                    "WORK_MODE_PARTIAL", "info", "آگهی ترکیبی است و تا حدی با ترجیح شما سازگار است"
                )
            ]
        return [_reason("WORK_MODE_INCOMPATIBLE", "negative", "شیوه کار با ترجیح شما سازگار نیست")]
    if name == "location":
        level = d["level"]
        if level == "city":
            return [_reason("LOCATION_SAME_CITY", "positive", "آگهی در شهر شماست")]
        if level == "province":
            return [_reason("LOCATION_SAME_PROVINCE", "info", "آگهی در استان شماست")]
        return [_reason("LOCATION_DIFFERENT_PROVINCE", "negative", "آگهی در استان دیگری است")]
    if name == "salary":
        if d["within"]:
            return [
                _reason("SALARY_COMPATIBLE", "positive", "حقوق مورد انتظار شما در بازه آگهی است")
            ]
        return [
            _reason(
                "SALARY_ABOVE_RANGE", "negative", "حقوق مورد انتظار شما بالاتر از بازه آگهی است"
            )
        ]
    return []


# ------------------------------------------------------------------ hard constraints
def _hard_constraints(factors: dict, resume, post) -> list[str]:
    """Strong mismatches. They cap the score and are shown as warnings. They never remove a post."""

    def used(name):
        factor = factors.get(name)
        return factor if factor and factor.get("applicable") else None

    flags = []
    skills = used("skills")
    if skills and skills["details"]["required_total"] and not skills["details"]["required_matched"]:
        flags.append("NO_REQUIRED_SKILLS_MATCHED")
    location = used("location")
    if location and post.work_mode == "ON_SITE" and location["details"]["level"] == "different":
        flags.append("ON_SITE_IN_DIFFERENT_PROVINCE")
    experience = used("experience")
    if experience and experience["details"]["gap"] <= -2:
        flags.append("EXPERIENCE_FAR_BELOW")
    return flags


HARD_FLAG_TEXT = {
    "NO_REQUIRED_SKILLS_MATCHED": "هیچ‌یک از مهارت‌های ضروری آگهی در رزومه نیست",
    "ON_SITE_IN_DIFFERENT_PROVINCE": "آگهی حضوری است و در استان دیگری قرار دارد",
    "EXPERIENCE_FAR_BELOW": "سطح تجربه خیلی پایین‌تر از نیاز آگهی است",
}


# ------------------------------------------------------------------ main entry
def semantic_reason(similarity: float | None, available: bool, pending: bool) -> dict:
    if similarity is None:
        if pending:
            return _reason(
                "SEMANTIC_PENDING",
                "info",
                "شباهت متنی هنوز در حال محاسبه است؛ فعلاً فقط معیارهای ساختاری لحاظ شده",
            )
        return _reason(
            "SEMANTIC_UNAVAILABLE",
            "info",
            "شباهت متنی در دسترس نیست؛ امتیاز فقط از معیارهای ساختاری محاسبه شد",
        )
    if similarity >= 0.7:
        return _reason("SEMANTIC_SIMILAR", "positive", "متن رزومه و آگهی شباهت زیادی دارند")
    if similarity >= 0.4:
        return _reason("SEMANTIC_RELATED", "info", "متن رزومه و آگهی تا حدی مرتبط‌اند")
    return _reason("SEMANTIC_DISTANT", "negative", "متن رزومه و آگهی شباهت کمی دارند")


def normalize_similarity(cosine: float, kind: str) -> float:
    low, high = config()["SEMANTIC_RANGE"][kind]
    return max(0.0, min(1.0, (cosine - low) / (high - low)))


def score_pair(
    resume: ResumeFeatures,
    post: PostFeatures,
    *,
    cosine: float | None = None,
    provider_kind: str = "none",
    semantic_pending: bool = False,
) -> MatchResult:
    cfg = config()
    factors, reasons, applicable = {}, [], {}
    for name, function in FACTOR_FUNCTIONS.items():
        factor = function(resume, post)
        if factor is None:
            factors[name] = {"applicable": False}
            continue
        factors[name] = {
            "applicable": factor["value"] is not None,
            "weight": cfg["WEIGHTS"][name],
            **factor,
        }
        if factor["value"] is not None:
            applicable[name] = factor
        reasons += _explain(name, factor, resume, post)

    structured = None
    if applicable:
        total = sum(cfg["WEIGHTS"][n] for n in applicable)
        structured = sum(cfg["WEIGHTS"][n] * f["value"] for n, f in applicable.items()) / total

    semantic = None
    if cosine is not None and provider_kind in cfg["SEMANTIC_WEIGHT"]:
        semantic = normalize_similarity(cosine, provider_kind)
    reasons.append(semantic_reason(semantic, provider_kind != "none", semantic_pending))

    if structured is None and semantic is None:
        final = 0.0
        reasons.append(
            _reason("INSUFFICIENT_DATA", "info", "اطلاعات کافی برای امتیازدهی وجود ندارد")
        )
    elif semantic is None:
        final = structured
    elif structured is None:
        final = semantic
    else:
        weight = cfg["SEMANTIC_WEIGHT"][provider_kind]
        final = (1 - weight) * structured + weight * semantic

    flags = _hard_constraints(factors, resume, post)
    score = round(final * 100)
    capped = bool(flags) and score > cfg["HARD_CONSTRAINT_CAP"]
    if flags:
        if capped:
            score = cfg["HARD_CONSTRAINT_CAP"]
        reasons.append(
            _reason(
                "HARD_CONSTRAINT_WARNING",
                "negative",
                "هشدار ناسازگاری: " + "؛ ".join(HARD_FLAG_TEXT[f] for f in flags),
                flags=flags,
            )
        )
    return MatchResult(
        max(0, min(100, score)), structured, semantic, factors, reasons, flags, capped
    )


def top_reasons(reasons: list, limit: int = 3) -> list:
    """Most informative first: the hard-constraint warning, then other warnings, then positives,
    then the rest."""
    order = {"negative": 1, "positive": 2, "info": 3}

    def key(item):
        index, reason = item
        priority = 0 if reason["code"] == "HARD_CONSTRAINT_WARNING" else order[reason["polarity"]]
        return priority, index

    return [reason for _, reason in sorted(enumerate(reasons), key=key)[:limit]]
