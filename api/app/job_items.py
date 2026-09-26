"""One place that turns a Job row into the list-card shape every surface returns
(feed, For You, saved, tracker) — so a new card field can't reach one surface and not
the others."""
from app.models import Job
from app.schemas import JobListItem
from app.util import root_domain

ELIGIBILITY_FIELDS = (
    "term_season", "term_year", "degree_levels", "grad_year_min", "grad_year_max",
    "us_citizen_required", "us_person_required", "clearance_required", "workplace_type", "country",
)


def _num(value) -> float | None:
    return float(value) if value is not None else None


def job_list_item(job: Job, company_name: str, company_careers_url: str | None, **extra) -> JobListItem:
    return JobListItem(
        id=job.id,
        title=job.title,
        company_name=company_name,
        company_id=job.company_id,
        company_domain=root_domain(company_careers_url),
        location_normalized=job.location_normalized,
        remote=job.remote,
        department=job.department,
        employment_type=job.employment_type,
        experience_level=job.experience_level,
        tech_tags=job.tech_tags,
        sponsorship_flag=job.sponsorship_flag,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        pay_min=_num(job.pay_min),
        pay_max=_num(job.pay_max),
        pay_currency=job.pay_currency,
        pay_period=job.pay_period,
        pay_source=job.pay_source,
        **{f: getattr(job, f) for f in ELIGIBILITY_FIELDS},
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        is_active=bool(job.is_active),
        apply_url=job.apply_url,
        **extra,
    )
