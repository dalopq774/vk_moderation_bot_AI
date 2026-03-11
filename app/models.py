from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class MessageRecord:
    message_id: int
    peer_id: int
    chat_id: int
    from_id: int
    text: str
    created_at: int


@dataclass
class ContextMessage:
    from_id: int
    text: str
    created_at: int


@dataclass
class ModerationResult:
    flagged: bool
    risk_score: float
    categories: Dict[str, bool]
    category_scores: Dict[str, float]


@dataclass
class AlertPayload:
    from_id: int
    chat_id: int
    peer_id: int
    message_text: str
    context: List[ContextMessage]
    moderation: ModerationResult
    author_name: Optional[str] = None