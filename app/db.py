import json
import sqlite3
import time

from app.models import ContextMessage, MessageRecord


class Database:
    """Работа с SQLite-хранилищем бота."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def init(self) -> None:
        """Создание необходимых таблиц."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Все сообщения из бесед
        cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            peer_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            from_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """)

        cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_unique
        ON messages(message_id, peer_id)
        """)

        # Сработавшие алерты
        cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            peer_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            from_id INTEGER NOT NULL,
            risk_score REAL NOT NULL,
            categories_json TEXT NOT NULL,
            excerpt TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """)

        # Агрегированная статистика по нарушителям
        cur.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            chat_id INTEGER NOT NULL,
            alerts_count INTEGER NOT NULL DEFAULT 0,
            max_risk REAL NOT NULL DEFAULT 0,
            last_message_text TEXT,
            updated_at INTEGER NOT NULL,
            UNIQUE(user_id, chat_id)
        )
        """)

        conn.commit()
        conn.close()

    def save_message(self, message: MessageRecord) -> None:
        """Сохраняет сообщение, игнорируя дубли."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        try:
            cur.execute("""
            INSERT INTO messages (message_id, peer_id, chat_id, from_id, text, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (
                message.message_id,
                message.peer_id,
                message.chat_id,
                message.from_id,
                message.text,
                message.created_at,
            ))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conn.close()

    def get_recent_context(self, peer_id: int, limit: int):
        """Возвращает последние сообщения беседы."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        SELECT from_id, text, created_at
        FROM messages
        WHERE peer_id = ?
        ORDER BY id DESC
        LIMIT ?
        """, (peer_id, limit))

        rows = cur.fetchall()
        conn.close()

        rows.reverse()
        return [
            ContextMessage(from_id=row[0], text=row[1], created_at=row[2])
            for row in rows
        ]

    def save_alert(
        self,
        message_id: int,
        peer_id: int,
        chat_id: int,
        from_id: int,
        risk_score: float,
        categories: dict,
        excerpt: str,
    ) -> None:
        """Сохраняет инцидент в таблицу alerts."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO alerts (
            message_id, peer_id, chat_id, from_id,
            risk_score, categories_json, excerpt, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            message_id,
            peer_id,
            chat_id,
            from_id,
            risk_score,
            json.dumps(categories, ensure_ascii=False),
            excerpt,
            int(time.time()),
        ))

        conn.commit()
        conn.close()

    def upsert_user_stats(self, user_id: int, chat_id: int, risk_score: float, text: str) -> None:
        """Обновляет агрегированную статистику пользователя."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO user_stats (user_id, chat_id, alerts_count, max_risk, last_message_text, updated_at)
        VALUES (?, ?, 1, ?, ?, ?)
        ON CONFLICT(user_id, chat_id) DO UPDATE SET
            alerts_count = user_stats.alerts_count + 1,
            max_risk = CASE
                WHEN excluded.max_risk > user_stats.max_risk THEN excluded.max_risk
                ELSE user_stats.max_risk
            END,
            last_message_text = excluded.last_message_text,
            updated_at = excluded.updated_at
        """, (
            user_id,
            chat_id,
            risk_score,
            text,
            int(time.time()),
        ))

        conn.commit()
        conn.close()

    def get_last_violators(self, chat_id: int, limit: int = 10):
        """Последние пользователи, у которых срабатывал алерт."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        SELECT from_id, risk_score, excerpt, created_at
        FROM alerts
        WHERE chat_id = ?
        ORDER BY id DESC
        LIMIT ?
        """, (chat_id, limit))

        rows = cur.fetchall()
        conn.close()
        return rows

    def get_top_users(self, chat_id: int, limit: int = 10):
        """Топ пользователей по количеству срабатываний."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        cur.execute("""
        SELECT user_id, alerts_count, max_risk, last_message_text
        FROM user_stats
        WHERE chat_id = ?
        ORDER BY alerts_count DESC, max_risk DESC
        LIMIT ?
        """, (chat_id, limit))

        rows = cur.fetchall()
        conn.close()
        return rows