"""AI draft generation engine supporting Anthropic and OpenAI."""

from __future__ import annotations

from typing import Optional

from weeklyamp.core.models import AIProvider, AppConfig


def generate_draft(
    prompt: str,
    config: AppConfig,
    max_tokens_override: Optional[int] = None,
) -> tuple[str, str]:
    """Generate a draft using the configured AI provider.

    Returns (content, model_used).
    """
    if config.ai.provider == AIProvider.ANTHROPIC:
        return _generate_anthropic(prompt, config, max_tokens_override)
    elif config.ai.provider == AIProvider.OPENAI:
        return _generate_openai(prompt, config, max_tokens_override)
    else:
        raise ValueError(f"Unknown AI provider: {config.ai.provider}")


def _generate_anthropic(
    prompt: str, config: AppConfig, max_tokens_override: Optional[int] = None,
) -> tuple[str, str]:
    """Generate using the Anthropic API."""
    import anthropic

    max_tokens = max_tokens_override or config.ai.max_tokens

    client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY env var
    message = client.messages.create(
        model=config.ai.model,
        max_tokens=max_tokens,
        temperature=config.ai.temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    content = message.content[0].text
    return content, config.ai.model


def _generate_openai(
    prompt: str, config: AppConfig, max_tokens_override: Optional[int] = None,
) -> tuple[str, str]:
    """Generate using the OpenAI API."""
    import openai

    max_tokens = max_tokens_override or config.ai.max_tokens

    client = openai.OpenAI()  # uses OPENAI_API_KEY env var
    response = client.chat.completions.create(
        model=config.ai.model,
        max_tokens=max_tokens,
        temperature=config.ai.temperature,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    return content, config.ai.model
