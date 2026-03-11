import os
from dataclasses import dataclass
from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    vk_group_token: str
    vk_group_id: int
    admin_ids: list[int]
    risk_threshold: float
    context_messages: int
    db_path: str
    min_text_length: int


def load_settings() -> Settings:
    """Загружает настройки из .env."""
    vk_group_token = os.getenv("VK_GROUP_TOKEN", "").strip()
    vk_group_id = int(os.getenv("VK_GROUP_ID", "0"))
    admin_ids = [
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip()
    ]
    risk_threshold = float(os.getenv("RISK_THRESHOLD", "0.75"))
    context_messages = int(os.getenv("CONTEXT_MESSAGES", "3"))
    db_path = os.getenv("DB_PATH", "moderation.db").strip()
    min_text_length = int(os.getenv("MIN_TEXT_LENGTH", "1"))

    if not vk_group_token:
        raise RuntimeError("Не задан VK_GROUP_TOKEN")
    if not vk_group_id:
        raise RuntimeError("Не задан VK_GROUP_ID")
    if not admin_ids:
        raise RuntimeError("Не заданы ADMIN_IDS")

    return Settings(
        vk_group_token=vk_group_token,
        vk_group_id=vk_group_id,
        admin_ids=admin_ids,
        risk_threshold=risk_threshold,
        context_messages=context_messages,
        db_path=db_path,
        min_text_length=min_text_length,
    )