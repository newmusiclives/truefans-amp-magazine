"""AI draft generation engine supporting Anthropic and OpenAI."""

from __future__ import annotations

import logging
from typing import Optional

from weeklyamp.core.models import AIProvider, AppConfig

logger = logging.getLogger(__name__)


def generate_draft(
    prompt: str,
    config: AppConfig,
    max_tokens_override: Optional[int] = None,
    system_prompt: Optional[str] = None,
) -> tuple[str, str]:
    """Generate a draft using the configured AI provider.

    Returns (content, model_used).
    """
    if config.ai.provider == AIProvider.ANTHROPIC:
        return _generate_anthropic(prompt, config, max_tokens_override, system_prompt)
    elif config.ai.provider == AIProvider.OPENAI:
        return _generate_openai(prompt, config, max_tokens_override, system_prompt)
    else:
        raise ValueError(f"Unknown AI provider: {config.ai.provider}")


def _generate_anthropic(
    prompt: str, config: AppConfig, max_tokens_override: Optional[int] = None,
    system_prompt: Optional[str] = None,
) -> tuple[str, str]:
    """Generate using the Anthropic API."""
    import anthropic

    max_tokens = max_tokens_override or config.ai.max_tokens

    kwargs: dict = dict(
        model=config.ai.model,
        max_tokens=max_tokens,
        temperature=config.ai.temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    if system_prompt:
        kwargs["system"] = system_prompt

    try:
        client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var
        message = client.messages.create(**kwargs)
        content = message.content[0].text
        return content, config.ai.model
    except Exception:
        logger.exception("Anthropic API call failed")
        return "", config.ai.model


def _generate_openai(
    prompt: str, config: AppConfig, max_tokens_override: Optional[int] = None,
    system_prompt: Optional[str] = None,
) -> tuple[str, str]:
    """Generate using the OpenAI API."""
    import openai

    max_tokens = max_tokens_override or config.ai.max_tokens

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    try:
        client = openai.OpenAI()  # uses OPENAI_API_KEY env var
        response = client.chat.completions.create(
            model=config.ai.model,
            max_tokens=max_tokens,
            temperature=config.ai.temperature,
            messages=messages,
        )
        content = response.choices[0].message.content
        return content, config.ai.model
    except Exception:
        logger.exception("OpenAI API call failed")
        return "", config.ai.model
