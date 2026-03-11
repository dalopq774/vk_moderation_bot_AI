import json
import logging
import re
import time

import requests
from vk_api.bot_longpoll import VkBotEventType, VkBotLongPoll

from app.config import load_settings
from app.db import Database
from app.keyboards import build_alert_keyboard
from app.models import AlertPayload, MessageRecord
from app.moderation import DetoxifyModerator
from app.notifier import build_admin_alert
from app.vk_client import VKClient


# Базовый логгер проекта
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


class VKModeratorBot:
    """Основной класс бота модерации."""

    def __init__(self):
        self.settings = load_settings()
        self.db = Database(self.settings.db_path)
        self.db.init()

        self.vk = VKClient(
            group_token=self.settings.vk_group_token,
            group_id=self.settings.vk_group_id,
        )

        self.moderator = DetoxifyModerator(
            context_messages=self.settings.context_messages,
        )

    def should_skip_text(self, text: str) -> bool:
        """
        Пропускаем слишком короткие и бесполезные сообщения:
        - пустые
        - только ссылка
        - только символы/эмодзи
        """
        cleaned = text.strip()

        if len(cleaned) < self.settings.min_text_length:
            return True

        if re.fullmatch(r"https?://\S+", cleaned):
            return True

        if not re.search(r"[A-Za-zА-Яа-яЁё0-9]", cleaned):
            return True

        return False

    def process_message_event(self, event) -> None:
        """Обработка нового сообщения из беседы."""
        if event.type != VkBotEventType.MESSAGE_NEW:
            return

        if not getattr(event, "from_chat", False):
            return

        message = event.message
        text = (message.text or "").strip()

        if not text or self.should_skip_text(text):
            return

        # Сохраняем сообщение в модель
        record = MessageRecord(
            message_id=int(message.id),
            peer_id=int(message.peer_id),
            chat_id=int(event.chat_id),
            from_id=int(message.from_id),
            text=text,
            created_at=int(message.date),
        )

        # Сохраняем сообщение в БД
        self.db.save_message(record)

        # Достаём недавний контекст беседы
        context = self.db.get_recent_context(
            peer_id=record.peer_id,
            limit=self.settings.context_messages + 1,
        )
        previous_context = context[:-1] if context else []

        # Анализируем токсичность локальной моделью
        try:
            moderation = self.moderator.moderate(
                text=record.text,
                context_messages=previous_context,
            )
        except Exception as e:
            logging.exception("Ошибка локальной модели moderation: %s", e)
            return

        logging.info(
            "chat_id=%s from_id=%s risk=%.3f flagged=%s text=%s",
            record.chat_id,
            record.from_id,
            moderation.risk_score,
            moderation.flagged,
            record.text[:120],
        )

        # Если риск высокий — сохраняем инцидент и уведомляем админов
        if moderation.risk_score >= self.settings.risk_threshold or moderation.flagged:
            self.db.save_alert(
                message_id=record.message_id,
                peer_id=record.peer_id,
                chat_id=record.chat_id,
                from_id=record.from_id,
                risk_score=moderation.risk_score,
                categories=moderation.category_scores,
                excerpt=record.text[:500],
            )

            self.db.upsert_user_stats(
                user_id=record.from_id,
                chat_id=record.chat_id,
                risk_score=moderation.risk_score,
                text=record.text,
            )

            author_name = self.vk.get_user_name(record.from_id)

            alert_text = build_admin_alert(
                AlertPayload(
                    from_id=record.from_id,
                    chat_id=record.chat_id,
                    peer_id=record.peer_id,
                    message_text=record.text,
                    context=previous_context,
                    moderation=moderation,
                    author_name=author_name,
                )
            )

            keyboard = build_alert_keyboard(chat_id=record.chat_id)

            self.vk.send_to_admins(
                self.settings.admin_ids,
                alert_text,
                keyboard=keyboard,
            )

    def process_message_event_callback(self, event) -> None:
        """Обработка нажатий на callback-кнопки."""
        payload = event.object.payload or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}

        cmd = payload.get("cmd")
        viewer_user_id = int(event.object.user_id)
        peer_id = int(event.object.peer_id)
        event_id = str(event.object.event_id)

        if cmd == "last_violators":
            chat_id = int(payload["chat_id"])
            rows = self.db.get_last_violators(chat_id=chat_id, limit=10)

            if not rows:
                text = "Нарушителей пока нет."
            else:
                parts = ["Последние нарушители:\n"]
                for user_id, risk, excerpt, created_at in rows:
                    user_name = self.vk.get_user_name(user_id) or f"id{user_id}"
                    parts.append(
                        f'• [id{user_id}|{user_name}] ("id{user_id}") — '
                        f'риск {round(risk * 100)}% — {excerpt}'
                    )
                text = "\n".join(parts)

            self.vk.answer_callback_event(
                event_id,
                viewer_user_id,
                peer_id,
                "📋 Показал последних нарушителей",
            )
            self.vk.send_private_message(viewer_user_id, text)
            return

        if cmd == "top_users":
            chat_id = int(payload["chat_id"])
            rows = self.db.get_top_users(chat_id=chat_id, limit=10)

            if not rows:
                text = "Статистика пока пустая."
            else:
                parts = ["Топ пользователей по нарушениям:\n"]
                for user_id, alerts_count, max_risk, last_message_text in rows:
                    user_name = self.vk.get_user_name(user_id) or f"id{user_id}"
                    parts.append(
                        f'• [id{user_id}|{user_name}] ("id{user_id}") — '
                        f'{alerts_count} сраб. — макс. риск {round(max_risk * 100)}%'
                    )
                text = "\n".join(parts)

            self.vk.answer_callback_event(
                event_id,
                viewer_user_id,
                peer_id,
                "🏆 Показал топ пользователей",
            )
            self.vk.send_private_message(viewer_user_id, text)
            return

        self.vk.answer_callback_event(
            event_id,
            viewer_user_id,
            peer_id,
            "❓ Неизвестная команда",
        )

    def run(self) -> None:
        """Главный цикл longpoll с автоматическим переподключением."""
        logging.info("Бот запущен. Слушаю сообщения...")

        while True:
            try:
                self.vk.longpoll = VkBotLongPoll(
                    self.vk.session,
                    self.settings.vk_group_id,
                )

                for event in self.vk.longpoll.listen():
                    if event.type == VkBotEventType.MESSAGE_EVENT:
                        try:
                            self.process_message_event_callback(event)
                        except Exception as e:
                            logging.exception("Ошибка обработки callback: %s", e)
                        continue

                    try:
                        self.process_message_event(event)
                    except Exception as e:
                        logging.exception("Ошибка обработки события: %s", e)

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.ReadTimeout,
                ConnectionResetError,
                OSError,
            ) as e:
                logging.warning("LongPoll соединение оборвалось: %s", e)
                logging.info("Переподключаюсь через 5 секунд...")
                time.sleep(5)

            except Exception as e:
                logging.exception("Критическая ошибка longpoll: %s", e)
                logging.info("Повторная попытка через 10 секунд...")
                time.sleep(10)