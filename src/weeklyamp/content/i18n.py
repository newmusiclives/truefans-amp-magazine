"""Internationalization foundation.

Provides translation infrastructure for future multi-language editions.
Currently supports: English (default), Spanish, Portuguese, French.
"""

SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish (Español)",
    "pt": "Portuguese (Português)",
    "fr": "French (Français)",
}

# Newsletter UI strings — extend as needed
TRANSLATIONS = {
    "en": {
        "subscribe": "Subscribe Free",
        "unsubscribe": "Unsubscribe",
        "read_more": "Read More",
        "share": "Share This Issue",
        "powered_by": "Powered by TrueFans NEWSLETTERS",
        "weekly_digest": "Your Weekly Music Digest",
    },
    "es": {
        "subscribe": "Suscríbete Gratis",
        "unsubscribe": "Cancelar Suscripción",
        "read_more": "Leer Más",
        "share": "Compartir Este Número",
        "powered_by": "Impulsado por TrueFans NEWSLETTERS",
        "weekly_digest": "Tu Resumen Musical Semanal",
    },
    "pt": {
        "subscribe": "Inscreva-se Grátis",
        "unsubscribe": "Cancelar Inscrição",
        "read_more": "Leia Mais",
        "share": "Compartilhe Esta Edição",
        "powered_by": "Desenvolvido por TrueFans NEWSLETTERS",
        "weekly_digest": "Seu Resumo Musical Semanal",
    },
    "fr": {
        "subscribe": "S'abonner Gratuitement",
        "unsubscribe": "Se Désabonner",
        "read_more": "Lire la Suite",
        "share": "Partager Ce Numéro",
        "powered_by": "Propulsé par TrueFans NEWSLETTERS",
        "weekly_digest": "Votre Résumé Musical Hebdomadaire",
    },
}


def t(key: str, lang: str = "en") -> str:
    """Get translated string. Falls back to English if not found."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["en"]).get(key, TRANSLATIONS["en"].get(key, key))


def get_supported_languages() -> dict:
    return SUPPORTED_LANGUAGES


class TranslationManager:
    """AI-powered content translation using Claude API.

    Translates full newsletter articles into target languages.
    INACTIVE by default — requires i18n.enabled=true.
    """

    def __init__(self, repo, config) -> None:
        self.repo = repo
        self.config = config

    def translate_draft(self, draft_id: int, target_language: str) -> int | None:
        """Translate a draft into a target language using AI.

        Returns the translated_draft ID, or None on failure.
        """
        if not self.config.i18n.enabled:
            return None

        if target_language not in SUPPORTED_LANGUAGES:
            return None

        conn = self.repo._conn()
        draft = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        conn.close()
        if not draft:
            return None

        content = draft["content"]
        lang_name = SUPPORTED_LANGUAGES[target_language]

        prompt = (
            f"Translate the following newsletter article into {lang_name}. "
            f"Preserve all Markdown formatting, links, and structure. "
            f"Adapt cultural references where appropriate but keep the meaning intact. "
            f"Do NOT add translator notes or commentary — output only the translation.\n\n"
            f"{content}"
        )

        from weeklyamp.content.generator import generate_draft
        translated, model = generate_draft(prompt, self.config, max_tokens_override=3000)
        if not translated:
            return None

        # Save translated draft
        conn = self.repo._conn()
        cur = conn.execute(
            """INSERT INTO translated_drafts (draft_id, language, content, ai_model)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(draft_id, language) DO UPDATE SET content = ?, ai_model = ?""",
            (draft_id, target_language, translated, model, translated, model),
        )
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def translate_issue(self, issue_id: int, target_language: str) -> list[int]:
        """Translate all drafts for an issue into a target language."""
        if not self.config.i18n.enabled:
            return []

        drafts = self.repo.get_drafts_for_issue(issue_id)
        translated_ids = []
        for draft in drafts:
            if draft["status"] == "approved":
                tid = self.translate_draft(draft["id"], target_language)
                if tid:
                    translated_ids.append(tid)
        return translated_ids

    def get_translated_draft(self, draft_id: int, language: str) -> dict | None:
        """Get a translated version of a draft."""
        conn = self.repo._conn()
        row = conn.execute(
            "SELECT * FROM translated_drafts WHERE draft_id = ? AND language = ?",
            (draft_id, language),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_available_translations(self, draft_id: int) -> list[str]:
        """Get list of languages a draft has been translated into."""
        conn = self.repo._conn()
        rows = conn.execute(
            "SELECT language FROM translated_drafts WHERE draft_id = ?",
            (draft_id,),
        ).fetchall()
        conn.close()
        return [r["language"] for r in rows]
