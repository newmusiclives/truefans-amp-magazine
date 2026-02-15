"""Submission intake — three paths: web form, email, API."""

from __future__ import annotations

import json
from typing import Optional

from weeklyamp.db.repository import Repository


def process_web_submission(repo: Repository, form_data: dict) -> int:
    """Process a submission from the public web form."""
    links = form_data.get("links", "")
    if isinstance(links, str):
        links_list = [l.strip() for l in links.split("\n") if l.strip()]
    else:
        links_list = links

    return repo.create_submission(
        artist_name=form_data.get("artist_name", ""),
        title=form_data.get("title", ""),
        description=form_data.get("description", ""),
        artist_email=form_data.get("artist_email", ""),
        artist_website=form_data.get("artist_website", ""),
        artist_social=form_data.get("artist_social", ""),
        submission_type=form_data.get("submission_type", "new_release"),
        intake_method="web_form",
        release_date=form_data.get("release_date", ""),
        genre=form_data.get("genre", ""),
        links_json=json.dumps(links_list),
    )


def process_email_submission(repo: Repository, email_data: dict) -> int:
    """Process a submission from an email intake."""
    return repo.create_submission(
        artist_name=email_data.get("from_name", ""),
        title=email_data.get("subject", ""),
        description=email_data.get("body", ""),
        artist_email=email_data.get("from_email", ""),
        intake_method="email",
        links_json=json.dumps(email_data.get("links", [])),
        attachments_json=json.dumps(email_data.get("attachments", [])),
    )


def process_api_submission(repo: Repository, json_data: dict) -> int:
    """Process a submission from the TrueFans CONNECT API."""
    return repo.create_submission(
        artist_name=json_data.get("artist_name", ""),
        title=json_data.get("title", ""),
        description=json_data.get("description", ""),
        artist_email=json_data.get("artist_email", ""),
        artist_website=json_data.get("artist_website", ""),
        artist_social=json_data.get("artist_social", ""),
        submission_type=json_data.get("submission_type", "new_release"),
        intake_method="api",
        release_date=json_data.get("release_date", ""),
        genre=json_data.get("genre", ""),
        links_json=json.dumps(json_data.get("links", [])),
        attachments_json=json.dumps(json_data.get("attachments", [])),
        api_source=json_data.get("api_source", "truefans_connect"),
    )
