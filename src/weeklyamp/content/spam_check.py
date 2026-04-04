"""Newsletter spam score checker.

Analyzes newsletter content against common spam triggers
without requiring external APIs.
"""

from __future__ import annotations

import re
from typing import Optional


SPAM_WORDS = [
    "free", "guaranteed", "no obligation", "winner", "congratulations",
    "act now", "limited time", "urgent", "click here", "buy now",
    "earn money", "make money", "cash", "discount", "cheap",
    "lowest price", "order now", "subscribe now", "unbelievable",
    "incredible deal", "once in a lifetime", "100% free",
]

def check_spam_score(html_content: str, subject: str = "") -> dict:
    """Analyze newsletter content for spam triggers.

    Returns dict with score (0-100, lower is better), issues list, and recommendations.
    """
    issues = []
    score = 0
    text = re.sub(r'<[^>]+>', ' ', html_content).lower()
    text = ' '.join(text.split())

    # Check subject line
    if subject:
        subj_lower = subject.lower()
        if subject == subject.upper() and len(subject) > 5:
            issues.append("Subject line is ALL CAPS — major spam trigger")
            score += 20
        if "!" in subject and subject.count("!") > 1:
            issues.append(f"Subject has {subject.count('!')} exclamation marks")
            score += 10
        if any(w in subj_lower for w in ["free", "winner", "congratulations", "urgent"]):
            issues.append("Subject contains spam trigger words")
            score += 15
        if "re:" in subj_lower or "fwd:" in subj_lower:
            issues.append("Subject mimics a reply/forward — deceptive")
            score += 15

    # Check content for spam words
    spam_found = []
    for word in SPAM_WORDS:
        count = text.count(word.lower())
        if count > 0:
            spam_found.append(f'"{word}" ({count}x)')
    if spam_found:
        issues.append(f"Spam trigger words found: {', '.join(spam_found[:5])}")
        score += min(len(spam_found) * 3, 20)

    # Check image-to-text ratio
    img_count = html_content.lower().count("<img")
    word_count = len(text.split())
    if word_count < 50:
        issues.append("Very little text content — spam filters prefer text-heavy emails")
        score += 10
    if img_count > 5 and word_count < 200:
        issues.append(f"High image-to-text ratio ({img_count} images, {word_count} words)")
        score += 10

    # Check for missing elements
    if "unsubscribe" not in text:
        issues.append("No unsubscribe link found — required by law (CAN-SPAM)")
        score += 25

    if "list-unsubscribe" not in html_content.lower():
        issues.append("No List-Unsubscribe header reference — reduces deliverability")
        score += 5

    # Check link count
    link_count = html_content.lower().count("<a ")
    if link_count > 20:
        issues.append(f"Too many links ({link_count}) — spam filters flag excessive linking")
        score += 10

    # Recommendations
    recommendations = []
    if score > 30:
        recommendations.append("Review and remove spam trigger words from content")
    if score > 50:
        recommendations.append("Consider rewriting the subject line")
    if not issues:
        recommendations.append("Content looks clean — good deliverability expected")
    else:
        recommendations.append("Address the issues above before sending")

    # Cap score at 100
    score = min(score, 100)

    # Rating
    if score <= 10:
        rating = "Excellent"
    elif score <= 25:
        rating = "Good"
    elif score <= 50:
        rating = "Fair"
    else:
        rating = "Poor"

    return {
        "score": score,
        "rating": rating,
        "issues": issues,
        "recommendations": recommendations,
        "word_count": word_count,
        "link_count": link_count,
        "image_count": img_count,
    }
