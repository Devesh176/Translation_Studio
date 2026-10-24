"""
PromptManager — loads prompt templates from config/prompts.yaml
and renders them with the provided variables.

All prompt strings are sourced exclusively from the YAML config so that
prompt engineers can tune them without touching Python code.
"""
from __future__ import annotations

from typing import Dict, Optional

from packages.core.config_loader import get_prompts_config


class PromptManager:
    """Renders prompt messages from config/prompts.yaml templates."""

    # ------------------------------------------------------------------ #
    #  Low-level helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _get_template(key: str, field: str) -> str:
        """Fetch a specific field (system/user) from a named prompt block."""
        cfg = get_prompts_config()
        block = cfg.get(key)
        if not block:
            raise KeyError(f"Prompt key '{key}' not found in prompts.yaml")
        template = block.get(field)
        if template is None:
            raise KeyError(f"Field '{field}' not found under prompt key '{key}'")
        return template

    # ------------------------------------------------------------------ #
    #  Public API                                                          #
    # ------------------------------------------------------------------ #

    @classmethod
    def get_translation_messages(
        cls,
        text: str,
        src_lang: str,
        tgt_lang: str,
        user_prompt: Optional[str] = None,
    ) -> list[Dict[str, str]]:
        """
        Build the OpenRouter/LLM message list for document translation.

        Uses the ``translation_v1`` block from prompts.yaml.
        """
        sys_tmpl = cls._get_template("translation_v1", "system")
        usr_tmpl = cls._get_template("translation_v1", "user")

        sys_msg = sys_tmpl.format(source_language=src_lang, target_language=tgt_lang)
        usr_msg = usr_tmpl.format(
            source_language=src_lang,
            target_language=tgt_lang,
            content=text,
        )

        if user_prompt:
            usr_msg += f"\n\nRefinement Instruction: {user_prompt}"

        return [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": usr_msg},
        ]

    @classmethod
    def get_section_edit_messages(
        cls,
        source_text: str,
        current_translation: str,
        instruction: str,
        src_lang: str,
        tgt_lang: str,
    ) -> list[Dict[str, str]]:
        """
        Build the message list for section-level prompt-edit.

        Uses the ``section_edit_v1`` block from prompts.yaml.
        """
        sys_tmpl = cls._get_template("section_edit_v1", "system")
        usr_tmpl = cls._get_template("section_edit_v1", "user")

        sys_msg = sys_tmpl.format(
            source_language=src_lang,
            target_language=tgt_lang,
        )
        usr_msg = usr_tmpl.format(
            source_language=src_lang,
            target_language=tgt_lang,
            source_text=source_text,
            current_translation=current_translation,
            instruction=instruction,
        )

        return [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": usr_msg},
        ]

    @classmethod
    def get_feasibility_messages(
        cls, selected_text: str, instruction: str, kind: str, types: str, tgt_lang: str
    ) -> list[Dict[str, str]]:
        sys_msg = cls._get_template("feasibility_v1", "system").format(target_language=tgt_lang)
        usr_msg = cls._get_template("feasibility_v1", "user").format(
            kind=kind, types=types, selected_text=selected_text, instruction=instruction
        )
        return [{"role": "system", "content": sys_msg}, {"role": "user", "content": usr_msg}]

    @classmethod
    def get_selection_edit_messages(
        cls, items: str, context: str, instruction: str, src_lang: str, tgt_lang: str, multi: bool
    ) -> list[Dict[str, str]]:
        fmt = (
            'Return ONLY a JSON object mapping each item id to its edited text, e.g. {"id": "text"}.'
            if multi
            else "Return ONLY the edited text of the single item, with no quotes, labels or commentary."
        )
        sys_msg = cls._get_template("selection_edit_v1", "system").format(target_language=tgt_lang, format_rule=fmt)
        usr_msg = cls._get_template("selection_edit_v1", "user").format(
            source_language=src_lang, context=context or "(none)", items=items, instruction=instruction
        )
        return [{"role": "system", "content": sys_msg}, {"role": "user", "content": usr_msg}]

    @classmethod
    def get_semantic_eval_messages(
        cls,
        source_text: str,
        translated_text: str,
        src_lang: str,
        tgt_lang: str,
    ) -> list[Dict[str, str]]:
        """
        Build the message list for semantic QA evaluation.

        Uses the ``semantic_eval_v1`` block from prompts.yaml.
        """
        sys_tmpl = cls._get_template("semantic_eval_v1", "system")
        usr_tmpl = cls._get_template("semantic_eval_v1", "user")

        sys_msg = sys_tmpl.format(
            source_language=src_lang,
            target_language=tgt_lang,
        )
        usr_msg = usr_tmpl.format(
            source_language=src_lang,
            target_language=tgt_lang,
            source_text=source_text,
            translated_text=translated_text,
        )

        return [
            {"role": "system", "content": sys_msg},
            {"role": "user", "content": usr_msg},
        ]
