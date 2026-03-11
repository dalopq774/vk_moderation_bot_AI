from typing import List, Optional

from detoxify import Detoxify

from app.models import ContextMessage, ModerationResult


class DetoxifyModerator:
    """Локальная модерация текста через Detoxify."""

    def __init__(self, context_messages: int = 3):
        self.context_messages = context_messages
        self.model = Detoxify("multilingual")

    def moderate(
        self,
        text: str,
        context_messages: Optional[List[ContextMessage]] = None,
    ) -> ModerationResult:
        context_messages = context_messages or []

        # Склеиваем короткий контекст с текущим сообщением
        context_block = " ".join(
            m.text.strip()
            for m in context_messages[-self.context_messages:]
            if m.text and m.text.strip()
        )

        combined_text = text.strip()
        if context_block:
            combined_text = f"{context_block} [SEP] {combined_text}"

        raw_scores = self.model.predict(combined_text)

        category_scores = {}
        for key, value in raw_scores.items():
            try:
                category_scores[key] = float(value)
            except (TypeError, ValueError):
                category_scores[key] = 0.0

        toxicity = category_scores.get("toxicity", 0.0)
        insult = category_scores.get("insult", 0.0)
        threat = category_scores.get("threat", 0.0)
        obscene = category_scores.get("obscene", 0.0)
        severe_toxicity = category_scores.get("severe_toxicity", 0.0)
        identity_attack = category_scores.get("identity_attack", 0.0)
        sexual_explicit = category_scores.get("sexual_explicit", 0.0)

        risk_score = max(
            toxicity,
            insult,
            threat,
            obscene,
            severe_toxicity,
            identity_attack,
            sexual_explicit,
        )

        categories = {
            "toxicity": toxicity >= 0.70,
            "insult": insult >= 0.70,
            "threat": threat >= 0.50,
            "obscene": obscene >= 0.75,
            "severe_toxicity": severe_toxicity >= 0.50,
            "identity_attack": identity_attack >= 0.50,
            "sexual_explicit": sexual_explicit >= 0.60,
        }

        flagged = any(categories.values())

        return ModerationResult(
            flagged=flagged,
            risk_score=risk_score,
            categories=categories,
            category_scores=category_scores,
        )