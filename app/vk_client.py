import logging
import random

import vk_api
from vk_api.bot_longpoll import VkBotLongPoll
from vk_api.exceptions import ApiError


class VKClient:
    """Тонкая обёртка над VK API."""

    def __init__(self, group_token: str, group_id: int):
        self.session = vk_api.VkApi(token=group_token)
        self.api = self.session.get_api()
        self.longpoll = VkBotLongPoll(self.session, group_id)

        # Кэш имён пользователей, чтобы не дёргать users.get лишний раз
        self._user_name_cache: dict[int, str] = {}

    def send_private_message(self, user_id: int, text: str, keyboard: str | None = None) -> None:
        """Отправка ЛС пользователю."""
        params = {
            "user_id": user_id,
            "message": text,
            "random_id": random.randint(1, 2_147_483_647),
        }
        if keyboard:
            params["keyboard"] = keyboard

        self.api.messages.send(**params)

    def send_to_admins(self, admin_ids: list[int], text: str, keyboard: str | None = None) -> None:
        """Рассылка сообщения всем администраторам."""
        for admin_id in admin_ids:
            try:
                self.send_private_message(admin_id, text, keyboard=keyboard)
                logging.info("Уведомление отправлено админу %s", admin_id)
            except Exception as e:
                logging.exception("Не удалось отправить сообщение админу %s: %s", admin_id, e)

    def get_user_name(self, user_id: int) -> str | None:
        """Получение имени пользователя с простым кэшем."""
        if user_id in self._user_name_cache:
            return self._user_name_cache[user_id]

        try:
            users = self.api.users.get(user_ids=user_id)
            if users:
                user = users[0]
                first_name = user.get("first_name", "").strip()
                last_name = user.get("last_name", "").strip()
                full_name = f"{first_name} {last_name}".strip()
                if full_name:
                    self._user_name_cache[user_id] = full_name
                    return full_name
        except Exception:
            return None

        return None

    def answer_callback_event(self, event_id: str, user_id: int, peer_id: int, text: str) -> None:
        """Короткая всплывающая подсказка при нажатии на кнопку."""
        try:
            safe_text = text.replace("\\", "\\\\").replace('"', '\\"')
            self.api.messages.sendMessageEventAnswer(
                event_id=event_id,
                user_id=user_id,
                peer_id=peer_id,
                event_data=f'{{"type":"show_snackbar","text":"{safe_text}"}}',
            )
        except ApiError:
            pass