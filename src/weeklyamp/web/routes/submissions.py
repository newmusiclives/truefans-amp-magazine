"""Admin submission management routes."""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.submissions.review import SubmissionReviewer
from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()

REVIEW_STATES = ["submitted", "reviewed", "approved", "rejected", "scheduled", "published"]


@router.get("/", response_class=HTMLResponse)
async def submissions_page(state: str = ""):
    repo = get_repo()
    submissions = repo.get_submissions(review_state=state if state else None)
    return render("submissions.html",
        submissions=submissions, review_states=REVIEW_STATES,
        filter_state=state,
    )


@router.get("/{submission_id}", response_class=HTMLResponse)
async def submission_detail(submission_id: int):
    repo = get_repo()
    sub = repo.get_submission(submission_id)
    if not sub:
        return render("partials/alert.html", message="Submission not found.", level="error")
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("submission_detail.html",
        submission=sub, upcoming_issues=upcoming_issues,
        review_states=REVIEW_STATES,
    )


@router.post("/{submission_id}/review", response_class=HTMLResponse)
async def review_submission(submission_id: int):
    repo = get_repo()
    config = get_config()
    reviewer = SubmissionReviewer(repo, config)
    reviewer.review_submission(submission_id)
    sub = repo.get_submission(submission_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("submission_detail.html",
        submission=sub, upcoming_issues=upcoming_issues,
        review_states=REVIEW_STATES,
        message="Marked as reviewed.", level="success",
    )


@router.post("/{submission_id}/approve", response_class=HTMLResponse)
async def approve_submission(submission_id: int):
    repo = get_repo()
    config = get_config()
    reviewer = SubmissionReviewer(repo, config)
    reviewer.approve_submission(submission_id)
    sub = repo.get_submission(submission_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("submission_detail.html",
        submission=sub, upcoming_issues=upcoming_issues,
        review_states=REVIEW_STATES,
        message="Submission approved.", level="success",
    )


@router.post("/{submission_id}/reject", response_class=HTMLResponse)
async def reject_submission(submission_id: int, notes: str = Form("")):
    repo = get_repo()
    config = get_config()
    reviewer = SubmissionReviewer(repo, config)
    reviewer.reject_submission(submission_id, notes)
    sub = repo.get_submission(submission_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("submission_detail.html",
        submission=sub, upcoming_issues=upcoming_issues,
        review_states=REVIEW_STATES,
        message="Submission rejected.", level="warning",
    )


@router.post("/{submission_id}/schedule", response_class=HTMLResponse)
async def schedule_submission(
    submission_id: int,
    issue_id: int = Form(...),
    section_slug: str = Form("artist_spotlight"),
):
    repo = get_repo()
    config = get_config()
    reviewer = SubmissionReviewer(repo, config)
    try:
        reviewer.schedule_submission(submission_id, issue_id, section_slug)
        reviewer.create_draft_from_submission(submission_id)
        message = "Submission scheduled and draft created."
        level = "success"
    except Exception as e:
        message = f"Failed: {e}"
        level = "error"

    sub = repo.get_submission(submission_id)
    upcoming_issues = repo.get_upcoming_issues(limit=10)
    return render("submission_detail.html",
        submission=sub, upcoming_issues=upcoming_issues,
        review_states=REVIEW_STATES,
        message=message, level=level,
    )
