"""Jinja2 template renderer for newsletter HTML."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from weeklyamp.web.sanitize import sanitize_html


def _get_template_dir() -> Path:
    """Find the templates directory."""
    # Walk up from this file to find templates/
    current = Path(__file__).parent.parent.parent.parent
    templates_dir = current / "templates"
    if templates_dir.exists():
        return templates_dir
    # Fallback: check cwd
    cwd_templates = Path.cwd() / "templates"
    if cwd_templates.exists():
        return cwd_templates
    raise FileNotFoundError("Cannot find templates/ directory")


def get_env() -> Environment:
    """Return a Jinja2 environment configured for newsletter templates."""
    return Environment(
        loader=FileSystemLoader(str(_get_template_dir())),
        autoescape=False,  # We handle HTML ourselves
    )


def render_section(display_name: str, content_html: str, headline: str = "") -> str:
    """Render a single section block."""
    env = get_env()
    template = env.get_template("section.html.j2")
    return template.render(display_name=display_name, content=content_html, headline=headline)


def render_newsletter(
    newsletter_name: str,
    tagline: str,
    issue_number: int,
    title: str,
    sections: list[dict],
    css: str = "",
    header_image_url: str = "",
    intro_copy: str = "",
    footer_html: str = "",
    ps_closing: str = "",
    edition_slug: str = "",
) -> str:
    """Render the full newsletter HTML.

    sections: list of {"html": str} dicts in order.
    edition_slug: if provided, uses edition-specific template (fan/artist/industry).
    """
    env = get_env()

    # Use edition-specific template if available, fall back to generic
    edition_template = f"edition_{edition_slug}.html.j2" if edition_slug else ""
    if edition_template:
        try:
            template = env.get_template(edition_template)
        except Exception:
            template = env.get_template("newsletter.html.j2")
    else:
        template = env.get_template("newsletter.html.j2")

    if not css:
        css_path = _get_template_dir() / "styles.css"
        if css_path.exists():
            css = css_path.read_text()

    return template.render(
        newsletter_name=newsletter_name,
        tagline=tagline,
        issue_number=issue_number,
        title=title,
        sections=sections,
        css=css,
        header_image_url=header_image_url,
        intro_copy=intro_copy,
        footer_html=footer_html,
        ps_closing=ps_closing,
    )


def render_guest_section(content_html: str, author_name: str = "", author_bio: str = "", original_url: str = "") -> str:
    """Render a guest column section with attribution block."""
    env = get_env()
    template = env.get_template("guest_section.html.j2")
    return template.render(
        content=sanitize_html(content_html),
        author_name=sanitize_html(author_name),
        author_bio=sanitize_html(author_bio),
        original_url=original_url,
    )


def render_submission_section(
    content_html: str,
    section_title: str = "ARTIST SPOTLIGHT",
    artist_name: str = "",
    artist_website: str = "",
    artist_social: str = "",
) -> str:
    """Render an artist submission section with artist info block."""
    env = get_env()
    template = env.get_template("submission_section.html.j2")
    return template.render(
        content=sanitize_html(content_html),
        section_title=sanitize_html(section_title),
        artist_name=sanitize_html(artist_name),
        artist_website=artist_website,
        artist_social=sanitize_html(artist_social),
    )


def render_sponsor_block(block: dict) -> str:
    """Render a single sponsor ad block for email."""
    env = get_env()
    template = env.get_template("sponsor_block.html.j2")
    sanitized = dict(block)
    if sanitized.get("body_html"):
        sanitized["body_html"] = sanitize_html(sanitized["body_html"])
    if sanitized.get("headline"):
        sanitized["headline"] = sanitize_html(sanitized["headline"])
    return template.render(block=sanitized)
