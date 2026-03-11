from app.models import AlertPayload


CATEGORY_LABELS = {
    "toxicity": "токсичность",
    "severe_toxicity": "сильная токсичность",
    "insult": "оскорбление",
    "threat": "угроза",
    "obscene": "нецензурная лексика",
    "identity_attack": "атака по признаку",
    "sexual_explicit": "сексуальный контент",
}


def short_text(text: str, limit: int = 500) -> str:
    """Обрезает слишком длинный текст."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit - 1] + "…"


def vk_user_link(user_id: int, name: str | None = None, with_quoted_id: bool = False) -> str:
    """Формирует кликабельное VK-упоминание."""
    display_name = (name or f"id{user_id}").strip()
    mention = f"[id{user_id}|{display_name}]"
    if with_quoted_id:
        return f'{mention} ("id{user_id}")'
    return mention


def format_context(context) -> str:
    """Форматирует контекст последних сообщений."""
    if not context:
        return "(контекст отсутствует)"

    lines = []
    for item in context[-5:]:
        lines.append(f"• id{item.from_id}: {short_text(item.text, 180)}")
    return "\n".join(lines)


def format_reasons(category_scores: dict, categories: dict) -> str:
    """Возвращает человекочитаемые причины срабатывания."""
    reasons = []

    for key, is_active in categories.items():
        if not is_active:
            continue

        score = float(category_scores.get(key, 0.0))
        label = CATEGORY_LABELS.get(key, key)
        reasons.append(f"— {label} ({round(score * 100)}%)")

    if reasons:
        return "\n".join(reasons)

    top_scores = sorted(
        category_scores.items(),
        key=lambda x: x[1] if x[1] is not None else 0.0,
        reverse=True,
    )[:2]

    fallback = []
    for key, score in top_scores:
        label = CATEGORY_LABELS.get(key, key)
        fallback.append(f"— {label} ({round(float(score) * 100)}%)")

    return "\n".join(fallback) if fallback else "(не определено)"


def build_admin_alert(payload: AlertPayload) -> str:
    """Собирает текст уведомления админу."""
    moderation = payload.moderation
    risk_percent = round(moderation.risk_score * 100)

    reasons = format_reasons(
        category_scores=moderation.category_scores,
        categories=moderation.categories,
    )

    author_line = vk_user_link(
        user_id=payload.from_id,
        name=payload.author_name,
        with_quoted_id=True,
    )

    return (
        "⚠️ Возможное нарушение правил\n\n"
        f"👤 Автор: {author_line}\n"
        f"💬 Беседа: chat_id={payload.chat_id}\n\n"
        f"📝 Сообщение:\n"
        f"“{short_text(payload.message_text, 900)}”\n\n"
        f"📌 Причина срабатывания:\n{reasons}\n\n"
        f"🎯 Риск: {risk_percent}%\n\n"
        f"📚 Последние сообщения:\n{format_context(payload.context)}\n\n"
        "Рекомендация: проверить сообщение вручную."
    )