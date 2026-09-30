"""Private SQLite accounts, single-use invitations and revocable sessions."""
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
import time

DB = Path(os.environ.get('ZQ_CMS_AUTH_DB', Path(__file__).parent / 'private' / 'accounts.sqlite3'))


def connect():
    db = sqlite3.connect(DB, timeout=15)
    db.row_factory = sqlite3.Row
    return db


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600000).hex()
    return salt + ':' + digest


def initialize(account=None, password=None):
    DB.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, account TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL, role TEXT NOT NULL, created INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS invites (
                id INTEGER PRIMARY KEY, token TEXT NOT NULL UNIQUE,
                creator INTEGER NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL,
                used_by INTEGER, revoked INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY, user_id INTEGER NOT NULL, csrf TEXT NOT NULL, expires INTEGER NOT NULL);
        ''')
        if not db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
            if not isinstance(account, str) or not account.strip() or not isinstance(password, str):
                raise RuntimeError('首次启动请配置管理员账号和密码')
            if not 12 <= len(password) <= 1024:
                raise RuntimeError('首次初始化管理员密码必须为 12 至 1024 字符')
            db.execute('INSERT INTO users(account,password,role,created) VALUES(?,?,?,?)',
                       (account.strip(), password_hash(password), 'admin', int(time.time())))
    DB.chmod(0o600)


def session(token):
    if not token: return None
    with connect() as db:
        row = db.execute('''SELECT u.id,u.account,u.role,s.csrf FROM sessions s
                            JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?''',
                         (hashed(token), int(time.time()))).fetchone()
        return dict(row) if row else None


def new_session(db, user_id):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = int(time.time())
    db.execute('DELETE FROM sessions WHERE expires<=?', (now,))
    db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (hashed(token), user_id, csrf, now + 43200))
    return token, csrf


def login(account, password):
    if not isinstance(account, str) or not isinstance(password, str) or len(password)>1024:
        return None
    with connect() as db:
        user = db.execute('SELECT * FROM users WHERE account=?', (account.strip(),)).fetchone()
        stored = user['password'] if user else '00'*16+':'+'00'*32
        valid = hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)
        return new_session(db, user['id']) if user and valid else None


def logout(token):
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE token=?', (hashed(token),))


def invite(creator):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with connect() as db:
        cursor = db.execute('INSERT INTO invites(token,creator,created,expires) VALUES(?,?,?,?)',
                            (hashed(token), creator, now, now + 7*86400))
        return {'id': cursor.lastrowid, 'token': token, 'expires': now + 7*86400}


def invitations():
    with connect() as db:
        return [dict(row) for row in db.execute('''SELECT i.id,i.created,i.expires,i.revoked,u.account AS registered
            FROM invites i LEFT JOIN users u ON i.used_by=u.id ORDER BY i.id DESC LIMIT 50''')]


def revoke(invite_id):
    with connect() as db:
        db.execute('UPDATE invites SET revoked=1 WHERE id=? AND used_by IS NULL', (invite_id,))


def valid_invite(db, token):
    return db.execute('SELECT * FROM invites WHERE token=? AND revoked=0 AND used_by IS NULL AND expires>?',
                      (hashed(token), int(time.time()))).fetchone()


def check_invite(token):
    with connect() as db:
        row = valid_invite(db, token)
        if not row: raise ValueError('邀请链接已使用、已取消或已过期，请联系管理员重新邀请。')
        return {'expires': row['expires']}


def register(token, phone, password):
    if not isinstance(phone, str) or not re.fullmatch(r'(?:[0-9]{8}|[0-9]{11})', phone.strip()):
        raise ValueError('请输入 8 位香港手机号或 11 位内地手机号，不用填写区号。')
    if not isinstance(password, str) or len(password)<8:
        raise ValueError('密码至少需要 8 位。')
    if len(password)>1024: raise ValueError('密码过长。')
    encoded = password_hash(password)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        invitation = valid_invite(db, token)
        if not invitation: raise ValueError('邀请链接已使用、已取消或已过期，请联系管理员重新邀请。')
        try:
            user = db.execute('INSERT INTO users(account,password,role,created) VALUES(?,?,?,?)',
                              (phone.strip(), encoded, 'editor', int(time.time())))
        except sqlite3.IntegrityError:
            raise ValueError('这个手机号已有账号，请直接登录。') from None
        db.execute('UPDATE invites SET used_by=? WHERE id=?', (user.lastrowid, invitation['id']))
        return new_session(db, user.lastrowid)
