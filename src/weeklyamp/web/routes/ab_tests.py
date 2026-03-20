"""A/B test management routes (admin)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from weeklyamp.web.deps import get_config, get_repo, render

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_class=HTMLResponse)
async def ab_tests_page():
    cfg = get_config()

    if not cfg.ab_testing.enabled:
        return render("ab_tests.html", enabled=False, tests=[], config=cfg)

    repo = get_repo()
    conn = repo._conn()
    tests = conn.execute(
        "SELECT * FROM ab_tests ORDER BY created_at DESC"
    ).fetchall()
    tests = [dict(r) for r in tests]

    # Attach results for each test
    for test in tests:
        results = conn.execute(
            "SELECT * FROM ab_test_results WHERE test_id = ? ORDER BY variant",
            (test["id"],),
        ).fetchall()
        test["results"] = [dict(r) for r in results]

    conn.close()

    return render("ab_tests.html", enabled=True, tests=tests, config=cfg)


@router.post("/create", response_class=HTMLResponse)
async def create_test(
    issue_id: int = Form(...),
    test_type: str = Form(...),
    variant_a: str = Form(...),
    variant_b: str = Form(...),
):
    cfg = get_config()
    if not cfg.ab_testing.enabled:
        return render("partials/alert.html",
            message="A/B testing is not enabled. Set ab_testing.enabled: true in config.",
            level="error")

    repo = get_repo()
    try:
        conn = repo._conn()
        conn.execute(
            """INSERT INTO ab_tests (issue_id, test_type, variant_a, variant_b, status, created_at)
               VALUES (?, ?, ?, ?, 'running', datetime('now'))""",
            (issue_id, test_type, variant_a, variant_b),
        )
        conn.commit()
        conn.close()

        return render("partials/alert.html",
            message=f"A/B test created for issue #{issue_id} ({test_type}).",
            level="success")
    except Exception as exc:
        return render("partials/alert.html",
            message=f"Failed to create test: {exc}", level="error")


@router.post("/{test_id}/evaluate", response_class=HTMLResponse)
async def evaluate_test(test_id: int):
    cfg = get_config()
    if not cfg.ab_testing.enabled:
        return render("partials/alert.html",
            message="A/B testing is not enabled.", level="error")

    repo = get_repo()
    try:
        conn = repo._conn()
        test = conn.execute(
            "SELECT * FROM ab_tests WHERE id = ?", (test_id,)
        ).fetchone()

        if not test:
            conn.close()
            return render("partials/alert.html",
                message="Test not found.", level="error")

        # Get results for each variant
        results = conn.execute(
            "SELECT * FROM ab_test_results WHERE test_id = ? ORDER BY variant",
            (test_id,),
        ).fetchall()
        results = [dict(r) for r in results]

        # Determine winner by open rate, then click rate
        winner = None
        if len(results) >= 2:
            a = results[0]
            b = results[1]
            a_score = (a.get("opens", 0) / max(a.get("sends", 1), 1))
            b_score = (b.get("opens", 0) / max(b.get("sends", 1), 1))
            winner = a.get("variant", "A") if a_score >= b_score else b.get("variant", "B")

        # Update test status
        conn.execute(
            "UPDATE ab_tests SET status = 'complete', winner = ? WHERE id = ?",
            (winner, test_id),
        )
        conn.commit()
        conn.close()

        return render("partials/alert.html",
            message=f"Test #{test_id} evaluated. Winner: Variant {winner}.",
            level="success")
    except Exception as exc:
        return render("partials/alert.html",
            message=f"Evaluation failed: {exc}", level="error")
