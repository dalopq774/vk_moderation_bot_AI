from vk_api.keyboard import VkKeyboard, VkKeyboardColor


def build_alert_keyboard(chat_id: int) -> str:
    """
    Клавиатура под сообщением-алертом для администраторов.
    """
    kb = VkKeyboard(inline=True)

    kb.add_callback_button(
        label="Последние нарушители",
        color=VkKeyboardColor.SECONDARY,
        payload={"cmd": "last_violators", "chat_id": chat_id},
    )
    kb.add_callback_button(
        label="Топ токсичных",
        color=VkKeyboardColor.PRIMARY,
        payload={"cmd": "top_users", "chat_id": chat_id},
    )

    return kb.get_keyboard()