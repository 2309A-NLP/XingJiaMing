import sqlite3, json, os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'chats.db')

class ChatStore:
    def __init__(self, db_path=None):
        self._path = db_path or DB_PATH
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        self._init_db()

    def _conn(self):
        return sqlite3.connect(self._path)

    def _init_db(self):
        with self._conn() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS chats (id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at REAL NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL, sources TEXT, timestamp REAL NOT NULL)')
            # 兼容旧表：补上缺失的列
            cols = [row[1] for row in conn.execute('PRAGMA table_info(messages)').fetchall()]
            if 'query_analysis' not in cols:
                conn.execute('ALTER TABLE messages ADD COLUMN query_analysis TEXT')
            if 'response_time' not in cols:
                conn.execute('ALTER TABLE messages ADD COLUMN response_time REAL')
            if 'search_config' not in cols:
                conn.execute('ALTER TABLE messages ADD COLUMN search_config TEXT')

    def create_chat(self, chat_id, title):
        now = datetime.now().timestamp()
        with self._conn() as conn:
            conn.execute('INSERT INTO chats VALUES (?, ?, ?)', (chat_id, title, now))
        return {"id": chat_id, "title": title, "created_at": now}

    def add_message(self, chat_id, msg_id, role, content, sources=None, timestamp=None, query_analysis=None, response_time=None, search_config=None):
        ts = timestamp or datetime.now().timestamp()
        sj = json.dumps(sources, ensure_ascii=False) if sources else None
        qa = json.dumps(query_analysis, ensure_ascii=False) if query_analysis else None
        sc = json.dumps(search_config, ensure_ascii=False) if search_config else None
        with self._conn() as conn:
            conn.execute('INSERT INTO messages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (msg_id, chat_id, role, content, sj, ts, qa, response_time, sc))

    def get_chats(self):
        with self._conn() as conn:
            rows = conn.execute('SELECT id, title, created_at FROM chats ORDER BY created_at DESC').fetchall()
        return [{"id": r[0], "title": r[1], "created_at": r[2]} for r in rows]

    def get_messages(self, chat_id):
        with self._conn() as conn:
            rows = conn.execute('SELECT id, role, content, sources, timestamp, query_analysis, response_time, search_config FROM messages WHERE chat_id = ? ORDER BY timestamp', (chat_id,)).fetchall()
        result = []
        for r in rows:
            msg = {"id": r[0], "role": r[1], "content": r[2], "timestamp": r[4]}
            if r[3]:
                msg["sources"] = json.loads(r[3])
            if r[5]:
                msg['query_analysis'] = json.loads(r[5])
            if r[6]:
                msg['response_time'] = r[6]
            if len(r) > 7 and r[7]:
                msg['search_config'] = json.loads(r[7])
            result.append(msg)
        return result

    def update_chat_title(self, chat_id, title):
        with self._conn() as conn:
            conn.execute('UPDATE chats SET title = ? WHERE id = ?', (title, chat_id))

    def delete_chat(self, chat_id):
        with self._conn() as conn:
            conn.execute('DELETE FROM messages WHERE chat_id = ?', (chat_id,))
            conn.execute('DELETE FROM chats WHERE id = ?', (chat_id,))
