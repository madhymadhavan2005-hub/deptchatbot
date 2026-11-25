import hashlib
import hmac
import os
import sqlite3
from pathlib import Path

DB_NAME = os.environ.get("DB_PATH", "dept_chat.db")


def hash_secret(secret: str) -> str:
    salt = os.urandom(16).hex()
    dk = hashlib.pbkdf2_hmac("sha256", secret.strip().encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${dk.hex()}"


def verify_secret(secret: str, stored_hash: str) -> bool:
    if not stored_hash or "$" not in stored_hash:
        return False
    salt, expected_hex = stored_hash.split("$", 1)
    dk = hashlib.pbkdf2_hmac("sha256", secret.strip().encode("utf-8"), salt.encode("utf-8"), 100_000)
    return hmac.compare_digest(dk.hex(), expected_hex)


# Format: (user_id, full_name, role, designation, batch, raw_password)
# - Mentor uses a unique 7-digit code (e.g., "7392841")
# - Students use their birth date in DDMMYYYY format (update each student's DOB as needed)
RAW_ROSTER = [
    ("FAC_BEN_01", "Dr. Ben M Jebin", "MENTOR", "Assistant Professor", "M.Sc AI & DS", "7392841"),
    ("PRK26AD1001", "SAMUEL JONATHAN", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1002", "AMAN TIGGA", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1003", "SEEMA EKKA", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1004", "KASTHURI K", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1005", "SUSMITHA R", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1006", "SIDDHESH", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1007", "JANET EPSI P", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1008", "AISWARIYA A Y", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1009", "D ASHIKKA", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1010", "SARULEGA M", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1011", "DHARSHINI", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1012", "SUBASH", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1013", "MOHAN RAM J", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1014", "SUSITH R", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1015", "MOHAMMED YUNUSH", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1016", "VISHNUVEL S", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1017", "MELVIN REENA J", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1018", "AQTHAR MAHMOOD R", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1019", "MANISHAA R", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1020", "ARUN JOSEPH A", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1021", "JEYA ILLANGUDI K P", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "30082005"),
    ("PRK26AD1022", "OM SWASTHIKA V", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1023", "MARKESHRUBIN D", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1024", "PRATEESH", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1025", "K SHARAN BALA CHANDER", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1027", "LALITH KISHORE", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
    ("PRK26AD1028", "RATHIDEVI", "STUDENT", "I M.Sc AI & DS", "Batch 2026", "01012005"),
]


def get_connection():
    db_path = Path(DB_NAME)
    if db_path.parent and str(db_path.parent) not in ("", "."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL,
            designation TEXT NOT NULL,
            batch TEXT NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            group_id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            description TEXT NOT NULL,
            mentor_only_post INTEGER DEFAULT 0,
            created_by TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            sender_id TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            content TEXT NOT NULL,
            attachment_url TEXT,
            attachment_name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_messages_group_id
        ON messages (group_id, id)
    """)

    cur.executemany(
        """
        INSERT OR IGNORE INTO users (user_id, full_name, role, designation, batch, password_hash)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (uid, name, role, desig, batch, hash_secret(pwd))
            for uid, name, role, desig, batch, pwd in RAW_ROSTER
        ],
    )

    for uid, name, role, desig, batch, pwd in RAW_ROSTER:
        clean_uid = uid.strip().upper()
        cur.execute("SELECT password_hash FROM users WHERE UPPER(user_id) = ?", (clean_uid,))
        existing = cur.fetchone()
        if existing:
            new_hash = existing["password_hash"] if verify_secret(pwd, existing["password_hash"]) else hash_secret(pwd)
            cur.execute(
                """
                UPDATE users
                SET full_name = ?, role = ?, designation = ?, batch = ?, password_hash = ?
                WHERE UPPER(user_id) = ?
                """,
                (name, role, desig, batch, new_hash, clean_uid),
            )

    cur.execute("SELECT COUNT(*) AS cnt FROM groups")
    if cur.fetchone()["cnt"] == 0:
        cur.executemany(
            """
            INSERT INTO groups (group_name, description, mentor_only_post, created_by)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("Official Notices & Circulars", "Mentor announcements only (Read-only for students)", 1, "FAC_BEN_01"),
                ("I M.Sc AI & DS — Class Discussion", "Open academic discussion & @bot queries", 0, "FAC_BEN_01"),
            ],
        )

    conn.commit()
    conn.close()


def update_user_password(user_id: str, new_secret: str) -> bool:
    clean_secret = (new_secret or "").strip()
    if not clean_secret:
        return False

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE UPPER(user_id) = UPPER(?)", (user_id.strip(),))
    row = cur.fetchone()
    if not row:
        conn.close()
        return False

    if row["role"] == "MENTOR" and not (clean_secret.isdigit() and len(clean_secret) == 7):
        conn.close()
        return False

    new_hash = hash_secret(clean_secret)
    cur.execute(
        "UPDATE users SET password_hash = ? WHERE UPPER(user_id) = UPPER(?)",
        (new_hash, user_id.strip()),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def authenticate_user(user_id: str, secret: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, full_name, role, designation, batch, password_hash
        FROM users
        WHERE UPPER(user_id) = UPPER(?)
        """,
        (user_id.strip(),),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    user_dict = dict(row)
    stored_hash = user_dict.pop("password_hash")

    if user_dict["role"] == "MENTOR":
        clean_code = secret.strip()
        if not (clean_code.isdigit() and len(clean_code) == 7):
            return None

    if not verify_secret(secret, stored_hash):
        return None

    return user_dict


def get_user(user_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT user_id, full_name, role, designation, batch FROM users WHERE UPPER(user_id) = UPPER(?)",
        (user_id.strip(),),
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, full_name, role, designation, batch
        FROM users
        ORDER BY CASE role WHEN 'MENTOR' THEN 0 ELSE 1 END, user_id ASC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_groups():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT group_id, group_name, description, mentor_only_post, created_by FROM groups ORDER BY group_id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_group(group_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT group_id, group_name, description, mentor_only_post, created_by FROM groups WHERE group_id = ?", (group_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def create_group(group_name: str, description: str, mentor_only_post: bool, created_by: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO groups (group_name, description, mentor_only_post, created_by)
        VALUES (?, ?, ?, ?)
        """,
        (group_name.strip(), description.strip(), 1 if mentor_only_post else 0, created_by),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return get_group(new_id)


def save_message(
    group_id: int,
    sender_id: str,
    sender_name: str,
    sender_role: str,
    content: str,
    attachment_url: str | None = None,
    attachment_name: str | None = None,
):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO messages (group_id, sender_id, sender_name, sender_role, content, attachment_url, attachment_name)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (group_id, sender_id, sender_name, sender_role, content, attachment_url, attachment_name),
    )
    msg_id = cur.lastrowid
    cur.execute(
        """
        SELECT id, group_id, sender_id, sender_name, sender_role, content, attachment_url, attachment_name, created_at
        FROM messages WHERE id = ?
        """,
        (msg_id,),
    )
    row = dict(cur.fetchone())
    conn.commit()
    conn.close()
    return row


def get_group_messages(group_id: int, limit: int = 100):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, group_id, sender_id, sender_name, sender_role, content, attachment_url, attachment_name, created_at
        FROM messages WHERE group_id = ? ORDER BY id ASC LIMIT ?
        """,
        (group_id, limit),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
[cite: 5]
