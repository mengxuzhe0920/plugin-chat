#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UC Chat —— 挂载在 sams-house.top/chat 的简约聊天服务（纯标准库）

- 身份：复用 Halo 站点 cookie（调 Halo /apis/api.console.halo.run/v1alpha1/users/-）
- 存储：SQLite（消息永久保存）
- 推送：WebSocket（手写 RFC 6455 握手 + 文本帧）
- HTTP：http.server.ThreadingHTTPServer
- 部署：127.0.0.1:8322，由 nginx 反代 /chat/

接口：
  GET  /chat/                       → 前端 HTML
  GET  /chat/api/me                 → 当前用户
  GET  /chat/api/rooms              → 会话列表
  POST /chat/api/rooms              → 建群 {title, member_names[]}
  POST /chat/api/dm                 → 私聊 {peer}
  POST /chat/api/join               → 加入群 {room_id}
  POST /chat/api/rooms/{id}/members → 邀请人进群 {member_names[]}（群成员可邀请）
  DELETE /chat/api/rooms/{id}       → 解散群（仅群主，消息一并删除）
  POST /chat/api/rooms/{id}/owner   → 转让群主 {new_owner}（仅群主，目标必须是群成员）
  POST /chat/api/rooms/{id}/leave   → 退出群聊（群主不可退，须先转让或解散）
  GET  /chat/api/rooms/{id}/members → 群成员名单（仅群成员可看，含群主/在线标识）
  GET  /chat/api/rooms/{id}/messages?limit=80&before=N
  GET  /chat/api/users              → 成员列表 + 在线
  POST /chat/api/upload             → 上传图片 {name, data(base64/dataURL)} → {url}
  GET  /chat/uploads/<file>         → 图片静态服务（30d 缓存）
  GET  /chat/api/health             → 健康
  WS   /chat/ws                     → 实时通道
    客户端 → {type:'join', room}, {type:'leave', room}, {type:'msg', room, content[, kind]}
    服务端 → {type:'msg', ...}, {type:'presence', online[]}, {type:'joined', room, online[]},
             {type:'members', room, members[]}, {type:'dissolved', room, title},
             {type:'room-added', room, title, by}
"""
import base64
import hashlib
import json
import os
import re
import socket
import sqlite3
import ssl
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------- 配置 ----------
BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, "uc_chat.db")
STATIC_DIR = os.path.join(BASE, "static")
UPLOAD_DIR = os.path.join(BASE, "uploads")
HALO_INTERNAL = os.environ.get("UC_HALO_INTERNAL", "http://127.0.0.1:8090")
LISTEN = os.environ.get("UC_LISTEN", "127.0.0.1")
PORT = int(os.environ.get("UC_PORT", "8322"))
SESSION_CACHE_TTL = 60
WS_MAGIC = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
UPLOAD_MAX_BYTES = 5 * 1024 * 1024          # 单张图片 5MB
UPLOAD_MAX_FILE_BYTES = 10 * 1024 * 1024    # 其他文件 10MB
UPLOAD_MAX_FILES = 3000                     # 磁盘上最多留这么多张，超出清理最旧
IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".gif": "image/gif", ".webp": "image/webp"}
# 普通文件白名单（ext -> content-type）
FILE_EXTS = {
    ".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown",
    ".doc": "application/msword", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint", ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv", ".json": "application/json", ".zip": "application/zip",
    ".rar": "application/vnd.rar", ".7z": "application/x-7z-compressed",
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".mp4": "video/mp4",
    ".apk": "application/vnd.android.package-archive",
}
ALLOWED_EXTS = dict(IMAGE_EXTS)
ALLOWED_EXTS.update(FILE_EXTS)
# 魔术字节校验（防伪装文件）
_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", (".png",)),
    (b"\xff\xd8\xff", (".jpg", ".jpeg")),
    (b"GIF87a", (".gif",)), (b"GIF89a", (".gif",)),
    (b"RIFF", (".webp",)),  # WEBP：RIFF????WEBP，下面再查 WEBP 字样
)

# ---------- DB ----------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    name TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    avatar TEXT,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rooms (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    owner TEXT,
    created_at INTEGER NOT NULL,
    dm_key TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS members (
    room_id TEXT NOT NULL,
    username TEXT NOT NULL,
    joined_at INTEGER NOT NULL,
    PRIMARY KEY (room_id, username)
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    sender_display TEXT NOT NULL,
    sender_avatar TEXT,
    content TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'text',
    fname TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_room ON messages(room_id, id);
CREATE INDEX IF NOT EXISTS idx_members_user ON members(username);
"""

_db_lock = threading.Lock()
_db = sqlite3.connect(DB_PATH, check_same_thread=False)
_db.row_factory = sqlite3.Row
with _db_lock:
    _db.executescript(SCHEMA)
    # 迁移：老库补 kind 列（图片消息）
    cols = [r["name"] for r in _db.execute("PRAGMA table_info(messages)").fetchall()]
    if "kind" not in cols:
        _db.execute("ALTER TABLE messages ADD COLUMN kind TEXT NOT NULL DEFAULT 'text'")
    # 迁移：老库补 fname 列（文件消息的原始文件名）
    cols = [r["name"] for r in _db.execute("PRAGMA table_info(messages)").fetchall()]
    if "fname" not in cols:
        _db.execute("ALTER TABLE messages ADD COLUMN fname TEXT")
    _db.commit()

os.makedirs(UPLOAD_DIR, exist_ok=True)


def _prune_uploads():
    """uploads 目录超量时删最旧的文件（按 mtime）"""
    try:
        files = [os.path.join(UPLOAD_DIR, f) for f in os.listdir(UPLOAD_DIR)]
        files = [f for f in files if os.path.isfile(f)]
        if len(files) <= UPLOAD_MAX_FILES:
            return
        files.sort(key=os.path.getmtime)
        for f in files[: len(files) - UPLOAD_MAX_FILES]:
            try:
                os.remove(f)
            except OSError:
                pass
    except OSError:
        pass


def _looks_like_image(raw: bytes, ext: str) -> bool:
    for magic, exts in _IMAGE_MAGIC:
        if raw.startswith(magic) and ext in exts:
            if magic == b"RIFF":
                return raw[8:12] == b"WEBP"
            return True
    return False


def db_exec(sql, params=()):
    with _db_lock:
        cur = _db.execute(sql, params)
        _db.commit()
        return cur


def db_query(sql, params=()):
    with _db_lock:
        cur = _db.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


# ---------- Halo 身份识别 ----------
_session_cache: dict = {}
_cache_lock = threading.Lock()


def resolve_user(cookie_header: str):
    """把浏览器 cookie 转发给 Halo 内部端口，拿当前用户。"""
    if not cookie_header:
        return None
    now = time.time()
    with _cache_lock:
        cached = _session_cache.get(cookie_header)
        if cached and cached[0] > now:
            return cached[1]
    try:
        last_err = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    f"{HALO_INTERNAL}/apis/api.console.halo.run/v1alpha1/users/-",
                    headers={"Cookie": cookie_header, "User-Agent": "uc-chat/1.0"},
                )
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    body = resp.read().decode("utf-8", "ignore")
                j = json.loads(body)
                u = j.get("user") or {}
                meta = u.get("metadata") or {}
                spec = u.get("spec") or {}
                name = meta.get("name")
                if not name or name == "anonymousUser":
                    return None
                user = {
                    "name": name,
                    "displayName": spec.get("displayName") or name,
                    "avatar": spec.get("avatar") or "",
                    "email": spec.get("email") or "",
                }
                with _cache_lock:
                    _session_cache[cookie_header] = (now + SESSION_CACHE_TTL, user)
                ts = int(time.time())
                db_exec(
                    """INSERT INTO users(name, display_name, avatar, first_seen, last_seen)
                       VALUES(?,?,?,?,?)
                       ON CONFLICT(name) DO UPDATE SET
                         display_name=excluded.display_name,
                         avatar=excluded.avatar,
                         last_seen=excluded.last_seen""",
                    (user["name"], user["displayName"], user["avatar"], ts, ts),
                )
                return user
            except urllib.error.HTTPError as e:
                # 401/403 是明确未登录，重试无意义
                if e.code in (401, 403):
                    return None
                last_err = e
            except Exception as e:
                last_err = e
            if attempt < 2:
                time.sleep(0.3 * (attempt + 1))
        print(f"[resolve_user] {type(last_err).__name__} after 3 tries: {last_err}", flush=True)
        return None
    except Exception as e:
        print(f"[resolve_user] {type(e).__name__}: {e}", flush=True)
        return None


# ---------- WebSocket Hub ----------
class WSClient:
    """包装一个 WebSocket 连接"""
    def __init__(self, sock, username):
        self.sock = sock
        self.username = username
        self.lock = threading.Lock()
        self.alive = True

    def send_text(self, text: str):
        if not self.alive:
            return
        try:
            payload = text.encode("utf-8")
            header = bytearray([0x81])  # FIN + text
            n = len(payload)
            if n < 126:
                header.append(n)
            elif n < 65536:
                header.append(126)
                header.extend(struct.pack(">H", n))
            else:
                header.append(127)
                header.extend(struct.pack(">Q", n))
            with self.lock:
                self.sock.sendall(bytes(header) + payload)
        except Exception:
            self.alive = False


class Hub:
    def __init__(self):
        self.rooms: dict[str, set[WSClient]] = {}
        self.user_socks: dict[str, set[WSClient]] = {}
        self.lock = threading.Lock()

    def join(self, room_id, client):
        with self.lock:
            self.rooms.setdefault(room_id, set()).add(client)
            self.user_socks.setdefault(client.username, set()).add(client)

    def leave(self, room_id, client):
        with self.lock:
            if room_id in self.rooms:
                self.rooms[room_id].discard(client)
                if not self.rooms[room_id]:
                    self.rooms.pop(room_id, None)
            if client.username in self.user_socks:
                self.user_socks[client.username].discard(client)
                if not self.user_socks[client.username]:
                    self.user_socks.pop(client.username, None)

    def leave_all(self, client):
        with self.lock:
            for rid, socks in list(self.rooms.items()):
                if client in socks:
                    socks.discard(client)
                    if not socks:
                        self.rooms.pop(rid, None)
            if client.username in self.user_socks:
                self.user_socks[client.username].discard(client)
                if not self.user_socks[client.username]:
                    self.user_socks.pop(client.username, None)

    def online(self):
        with self.lock:
            return sorted(self.user_socks.keys())

    def broadcast(self, room_id, payload):
        text = json.dumps(payload, ensure_ascii=False)
        with self.lock:
            socks = list(self.rooms.get(room_id, set()))
        for c in socks:
            c.send_text(text)

    def send_to_user(self, username, payload):
        """推给某个用户的全部连接（用于邀请通知等非房间广播）"""
        text = json.dumps(payload, ensure_ascii=False)
        with self.lock:
            socks = list(self.user_socks.get(username, set()))
        for c in socks:
            c.send_text(text)


HUB = Hub()

# ---------- WebSocket 协议处理 ----------

def ws_read_frame(sock):
    """读一帧，返回 (opcode, payload_bytes)，连接断开返回 None"""
    try:
        head = b""
        while len(head) < 2:
            chunk = sock.recv(2 - len(head))
            if not chunk:
                return None
            head += chunk
        b1, b2 = head[0], head[1]
        opcode = b1 & 0x0F
        masked = (b2 & 0x80) != 0
        plen = b2 & 0x7F
        if plen == 126:
            ext = b""
            while len(ext) < 2:
                ext += sock.recv(2 - len(ext))
            plen = struct.unpack(">H", ext)[0]
        elif plen == 127:
            ext = b""
            while len(ext) < 8:
                ext += sock.recv(8 - len(ext))
            plen = struct.unpack(">Q", ext)[0]
        mask = b""
        if masked:
            while len(mask) < 4:
                mask += sock.recv(4 - len(mask))
        payload = b""
        while len(payload) < plen:
            chunk = sock.recv(min(65536, plen - len(payload)))
            if not chunk:
                return None
            payload += chunk
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        return opcode, payload
    except Exception:
        return None


def ws_send_pong(sock, payload=b""):
    try:
        header = bytearray([0x8A])
        n = len(payload)
        if n < 126:
            header.append(n)
        elif n < 65536:
            header.append(126)
            header.extend(struct.pack(">H", n))
        else:
            header.append(127)
            header.extend(struct.pack(">Q", n))
        sock.sendall(bytes(header) + payload)
    except Exception:
        pass


def ws_send_close(sock, code=1000):
    try:
        payload = struct.pack(">H", code)
        sock.sendall(bytes([0x88, len(payload)]) + payload)
    except Exception:
        pass


# ---------- HTTP Handler ----------

def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "UCChat/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass  # 静默

    # ---------- 工具 ----------
    def _send(self, code, body=b"", content_type="text/plain; charset=utf-8", extra_headers=None):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        if body:
            try:
                self.wfile.write(body)
            except Exception:
                pass

    def _send_json(self, obj, code=200):
        self._send(code, _json_bytes(obj), "application/json; charset=utf-8")

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return b""
        return self.rfile.read(length)

    def _read_json(self):
        body = self._read_body()
        if not body:
            return {}
        try:
            return json.loads(body.decode("utf-8", "ignore"))
        except Exception:
            return {}

    def _current_user(self):
        cookie = self.headers.get("Cookie") or ""
        return resolve_user(cookie)

    def do_HEAD(self):
        # 简单响应 200，避免某些健康检查报 501
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)

        # 前端
        if path in ("/chat", "/chat/"):
            html_path = os.path.join(STATIC_DIR, "index.html")
            try:
                with open(html_path, "rb") as f:
                    body = f.read()
                self._send(200, body, "text/html; charset=utf-8")
            except FileNotFoundError:
                self._send(404, "not found")
            return

        # WebSocket 升级
        if path == "/chat/ws":
            self._handle_ws()
            return

        # API
        if path == "/chat/api/health":
            self._send_json({"ok": True, "ts": int(time.time())})
            return

        if path == "/chat/api/me":
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            self._send_json({"ok": True, "user": user, "online": HUB.online()})
            return

        if path == "/chat/api/rooms":
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            rows = db_query(
                """SELECT r.id, r.kind, r.title, r.owner, r.created_at, r.dm_key,
                          (SELECT MAX(created_at) FROM messages WHERE room_id=r.id) AS last_at,
                          (SELECT content FROM messages WHERE room_id=r.id ORDER BY id DESC LIMIT 1) AS last_msg,
                          (SELECT sender_display FROM messages WHERE room_id=r.id ORDER BY id DESC LIMIT 1) AS last_sender,
                          (SELECT kind FROM messages WHERE room_id=r.id ORDER BY id DESC LIMIT 1) AS last_kind,
                          (SELECT COUNT(*) FROM members WHERE room_id=r.id) AS member_count
                   FROM rooms r
                   WHERE EXISTS(SELECT 1 FROM members m WHERE m.room_id=r.id AND m.username=?)
                   ORDER BY COALESCE(last_at, r.created_at) DESC""",
                (user["name"],),
            )
            for r in rows:
                mem = db_query("SELECT username FROM members WHERE room_id=?", (r["id"],))
                r["members"] = [m["username"] for m in mem]
                if r.get("last_kind") in ("image", "file") and r.get("last_msg"):
                    r["last_msg"] = "[图片]" if r["last_kind"] == "image" else "[文件]"
                if r["kind"] == "dm":
                    other = [m for m in r["members"] if m != user["name"]]
                    if other:
                        u = db_query(
                            "SELECT display_name, avatar FROM users WHERE name=?",
                            (other[0],),
                        )
                        if u:
                            r["title"] = u[0]["display_name"]
                            r["peer"] = other[0]
                            r["peer_avatar"] = u[0]["avatar"] or ""
            self._send_json({"ok": True, "rooms": rows})
            return

        m = re.match(r"^/chat/api/rooms/([A-Za-z0-9]+)/messages$", path)
        if m:
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            room_id = m.group(1)
            room = db_query("SELECT kind FROM rooms WHERE id=?", (room_id,))
            if not room:
                self._send_json({"ok": False, "detail": "room not found"}, 404)
                return
            # 只有成员能读消息（退群/被移出后立即失效，DM 两人同样校验）
            is_member = db_query(
                "SELECT 1 FROM members WHERE room_id=? AND username=?",
                (room_id, user["name"]),
            )
            if not is_member:
                self._send_json({"ok": False, "detail": "not a member"}, 403)
                return
            try:
                limit = int(query.get("limit", ["80"])[0])
                limit = max(1, min(limit, 200))
            except Exception:
                limit = 80
            try:
                before = int(query.get("before", ["0"])[0])
            except Exception:
                before = 0
            q = str(query.get("q", [""])[0] or "").strip()[:40]
            # LIKE 通配符转义（\ % _）
            q_like = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            q_filter = f"%{q_like}%" if q_like else None
            if before > 0:
                if q_filter:
                    rows = db_query(
                        """SELECT id, sender, sender_display, sender_avatar, content, kind, fname, created_at
                           FROM messages WHERE room_id=? AND id<?
                             AND (content LIKE ? ESCAPE '\\' OR fname LIKE ? ESCAPE '\\')
                           ORDER BY id DESC LIMIT ?""",
                        (room_id, before, q_filter, q_filter, limit),
                    )
                else:
                    rows = db_query(
                        """SELECT id, sender, sender_display, sender_avatar, content, kind, fname, created_at
                           FROM messages WHERE room_id=? AND id<? ORDER BY id DESC LIMIT ?""",
                        (room_id, before, limit),
                    )
            else:
                if q_filter:
                    rows = db_query(
                        """SELECT id, sender, sender_display, sender_avatar, content, kind, fname, created_at
                           FROM messages WHERE room_id=?
                             AND (content LIKE ? ESCAPE '\\' OR fname LIKE ? ESCAPE '\\')
                           ORDER BY id DESC LIMIT ?""",
                        (room_id, q_filter, q_filter, limit),
                    )
                else:
                    rows = db_query(
                        """SELECT id, sender, sender_display, sender_avatar, content, kind, fname, created_at
                           FROM messages WHERE room_id=? ORDER BY id DESC LIMIT ?""",
                        (room_id, limit),
                    )
            rows.reverse()
            self._send_json({"ok": True, "messages": rows})
            return

        m = re.match(r"^/chat/api/rooms/([A-Za-z0-9]+)/members$", path)
        if m:
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            rid = m.group(1)
            room = db_query("SELECT id, kind, title, owner FROM rooms WHERE id=?", (rid,))
            if not room:
                self._send_json({"ok": False, "detail": "room not found"}, 404)
                return
            room = room[0]
            is_member = db_query(
                "SELECT 1 FROM members WHERE room_id=? AND username=?",
                (rid, user["name"]),
            )
            if not is_member:
                self._send_json({"ok": False, "detail": "not a member"}, 403)
                return
            rows = db_query(
                """SELECT m.username, m.joined_at, u.display_name, u.avatar
                   FROM members m LEFT JOIN users u ON u.name=m.username
                   WHERE m.room_id=?""",
                (rid,),
            )
            online = set(HUB.online())
            members = []
            for r in rows:
                members.append({
                    "name": r["username"],
                    "display_name": r["display_name"] or r["username"],
                    "avatar": r["avatar"] or "",
                    "online": r["username"] in online,
                    "owner": room["kind"] == "group" and r["username"] == room["owner"],
                    "me": r["username"] == user["name"],
                    "joined_at": r["joined_at"],
                })
            # 群主置顶，其次在线，再按加入时间
            members.sort(key=lambda x: (not x["owner"], not x["online"], x["joined_at"]))
            self._send_json({
                "ok": True,
                "room": rid,
                "kind": room["kind"],
                "title": room["title"],
                "owner": room["owner"],
                "members": members,
            })
            return

        if path == "/chat/api/users":
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            rows = db_query(
                "SELECT name, display_name, avatar, last_seen FROM users ORDER BY last_seen DESC LIMIT 200"
            )
            self._send_json({"ok": True, "users": rows, "online": HUB.online()})
            return

        # 上传的文件/图片（同名只可能是 uuid，正则已挡掉路径穿越）
        m = re.match(r"^/chat/uploads/([A-Za-z0-9]+\.[A-Za-z0-9]{1,5})$", path)
        if m:
            fname = m.group(1)
            ext = os.path.splitext(fname)[1].lower()
            ctype = ALLOWED_EXTS.get(ext)
            if not ctype:
                self._send(404, "not found")
                return
            fpath = os.path.join(UPLOAD_DIR, fname)
            try:
                with open(fpath, "rb") as f:
                    body = f.read()
            except OSError:
                self._send(404, "not found")
                return
            self._send(200, body, ctype, {"Cache-Control": "public, max-age=2592000"})
            return

        self._send(404, "not found")

    # ---------- POST ----------
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/chat/api/rooms":
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            body = self._read_json()
            title = (body.get("title") or "").strip()
            if not title:
                self._send_json({"ok": False, "detail": "title required"}, 400)
                return
            if len(title) > 40:
                self._send_json({"ok": False, "detail": "title too long"}, 400)
                return
            rid = uuid.uuid4().hex[:12]
            ts = int(time.time())
            db_exec(
                "INSERT INTO rooms(id, kind, title, owner, created_at) VALUES(?,?,?,?,?)",
                (rid, "group", title, user["name"], ts),
            )
            db_exec(
                "INSERT INTO members(room_id, username, joined_at) VALUES(?,?,?)",
                (rid, user["name"], ts),
            )
            for m in body.get("member_names") or []:
                if m and m != user["name"]:
                    db_exec(
                        "INSERT OR IGNORE INTO members(room_id, username, joined_at) VALUES(?,?,?)",
                        (rid, m, ts),
                    )
            self._send_json({"ok": True, "id": rid})
            return

        m = re.match(r"^/chat/api/rooms/([A-Za-z0-9]+)/members$", path)
        if m:
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            rid = m.group(1)
            room = db_query("SELECT id, kind, title FROM rooms WHERE id=?", (rid,))
            if not room or room[0]["kind"] != "group":
                self._send_json({"ok": False, "detail": "room not found"}, 404)
                return
            is_member = db_query(
                "SELECT 1 FROM members WHERE room_id=? AND username=?", (rid, user["name"])
            )
            if not is_member:
                self._send_json({"ok": False, "detail": "not a member"}, 403)
                return
            body = self._read_json()
            names = [str(n).strip() for n in (body.get("member_names") or [])]
            names = [n for n in names if n and n != user["name"]][:50]
            if not names:
                self._send_json({"ok": False, "detail": "member_names required"}, 400)
                return
            # 只邀请访问过聊天的成员（与 /dm 同规则），避免拉入不存在的人
            existing = {r["name"] for r in db_query("SELECT name FROM users")}
            ts = int(time.time())
            added = []
            for n in names:
                if n not in existing:
                    continue
                cur = db_exec(
                    "INSERT OR IGNORE INTO members(room_id, username, joined_at) VALUES(?,?,?)",
                    (rid, n, ts),
                )
                if cur.rowcount:
                    added.append(n)
            mem = db_query("SELECT username FROM members WHERE room_id=?", (rid,))
            members = [x["username"] for x in mem]
            if added:
                HUB.broadcast(rid, {"type": "members", "room": rid, "members": members})
                # 在线的人实时收到「被拉进新群」通知
                for n in added:
                    HUB.send_to_user(n, {
                        "type": "room-added",
                        "room": rid,
                        "title": room[0]["title"],
                        "by": user["displayName"] or user["name"],
                    })
            self._send_json({"ok": True, "added": added, "members": members})
            return

        m = re.match(r"^/chat/api/rooms/([A-Za-z0-9]+)/owner$", path)
        if m:
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            rid = m.group(1)
            room = db_query("SELECT id, kind, title, owner FROM rooms WHERE id=?", (rid,))
            if not room or room[0]["kind"] != "group":
                self._send_json({"ok": False, "detail": "room not found"}, 404)
                return
            if room[0]["owner"] != user["name"]:
                self._send_json({"ok": False, "detail": "only owner can transfer"}, 403)
                return
            body = self._read_json()
            new_owner = (body.get("new_owner") or "").strip()
            if not new_owner:
                self._send_json({"ok": False, "detail": "new_owner required"}, 400)
                return
            if new_owner == user["name"]:
                self._send_json({"ok": False, "detail": "you are already the owner"}, 400)
                return
            is_member = db_query(
                "SELECT 1 FROM members WHERE room_id=? AND username=?", (rid, new_owner)
            )
            if not is_member:
                self._send_json({"ok": False, "detail": "target is not a member"}, 400)
                return
            db_exec("UPDATE rooms SET owner=? WHERE id=?", (new_owner, rid))
            nu = db_query("SELECT display_name FROM users WHERE name=?", (new_owner,))
            new_display = (nu[0]["display_name"] if nu else "") or new_owner
            HUB.broadcast(rid, {
                "type": "owner-changed",
                "room": rid,
                "owner": new_owner,
                "owner_display": new_display,
                "by": user["displayName"] or user["name"],
            })
            self._send_json({"ok": True, "owner": new_owner, "owner_display": new_display})
            return

        m = re.match(r"^/chat/api/rooms/([A-Za-z0-9]+)/leave$", path)
        if m:
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            rid = m.group(1)
            room = db_query("SELECT id, kind, title, owner FROM rooms WHERE id=?", (rid,))
            if not room or room[0]["kind"] != "group":
                self._send_json({"ok": False, "detail": "room not found"}, 404)
                return
            if room[0]["owner"] == user["name"]:
                self._send_json(
                    {"ok": False, "detail": "群主不能退群，请先转让群主或解散群"}, 403
                )
                return
            is_member = db_query(
                "SELECT 1 FROM members WHERE room_id=? AND username=?", (rid, user["name"])
            )
            if not is_member:
                self._send_json({"ok": False, "detail": "not a member"}, 400)
                return
            db_exec(
                "DELETE FROM members WHERE room_id=? AND username=?",
                (rid, user["name"]),
            )
            mem = db_query("SELECT username FROM members WHERE room_id=?", (rid,))
            members = [x["username"] for x in mem]
            HUB.broadcast(rid, {
                "type": "member-left",
                "room": rid,
                "user": user["name"],
                "user_display": user["displayName"] or user["name"],
                "members": members,
            })
            self._send_json({"ok": True, "members": members})
            return

        if path == "/chat/api/dm":
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            body = self._read_json()
            peer = (body.get("peer") or "").strip()
            if not peer or peer == user["name"]:
                self._send_json({"ok": False, "detail": "bad peer"}, 400)
                return
            exists = db_query("SELECT name FROM users WHERE name=?", (peer,))
            if not exists:
                self._send_json(
                    {"ok": False, "detail": "对方还没访问过聊天，无法私聊"}, 404
                )
                return
            a, b = sorted([user["name"], peer])
            key = f"{a}|{b}"
            row = db_query("SELECT id FROM rooms WHERE dm_key=?", (key,))
            if row:
                self._send_json({"ok": True, "id": row[0]["id"]})
                return
            rid = uuid.uuid4().hex[:12]
            ts = int(time.time())
            db_exec(
                "INSERT INTO rooms(id, kind, title, owner, created_at, dm_key) VALUES(?,?,?,?,?,?)",
                (rid, "dm", key, None, ts, key),
            )
            for u in (a, b):
                db_exec(
                    "INSERT INTO members(room_id, username, joined_at) VALUES(?,?,?)",
                    (rid, u, ts),
                )
            self._send_json({"ok": True, "id": rid})
            return

        if path == "/chat/api/join":
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            body = self._read_json()
            rid = (body.get("room_id") or "").strip()
            r = db_query("SELECT id, kind FROM rooms WHERE id=?", (rid,))
            if not r:
                self._send_json({"ok": False, "detail": "room not found"}, 404)
                return
            db_exec(
                "INSERT OR IGNORE INTO members(room_id, username, joined_at) VALUES(?,?,?)",
                (rid, user["name"], int(time.time())),
            )
            self._send_json({"ok": True})
            return

        if path == "/chat/api/upload":
            user = self._current_user()
            if not user:
                self._send_json({"ok": False, "detail": "not logged in"}, 401)
                return
            body = self._read_json()
            name = str(body.get("name") or "").strip()
            data = str(body.get("data") or "").strip()
            if data.startswith("data:"):
                data = data.split(",", 1)[-1]
            ext = os.path.splitext(name)[1].lower()
            if ext not in ALLOWED_EXTS:
                self._send_json({"ok": False, "detail": "unsupported file type"}, 400)
                return
            is_image = ext in IMAGE_EXTS
            max_bytes = UPLOAD_MAX_BYTES if is_image else UPLOAD_MAX_FILE_BYTES
            try:
                raw = base64.b64decode(data, validate=False)
            except Exception:
                self._send_json({"ok": False, "detail": "bad base64"}, 400)
                return
            if not raw or len(raw) > max_bytes:
                limit = "5MB" if is_image else "10MB"
                self._send_json({"ok": False, "detail": f"empty or too large (max {limit})"}, 400)
                return
            # 只对图片做魔术字节校验，其他文件不校验内容
            if is_image and not _looks_like_image(raw, ext):
                self._send_json({"ok": False, "detail": "not a real image"}, 400)
                return
            fname = uuid.uuid4().hex[:16] + ext
            fpath = os.path.join(UPLOAD_DIR, fname)
            try:
                with open(fpath, "wb") as f:
                    f.write(raw)
            except OSError as e:
                self._send_json({"ok": False, "detail": f"write failed: {e}"}, 500)
                return
            _prune_uploads()
            self._send_json({
                "ok": True,
                "url": f"/chat/uploads/{fname}",
                "size": len(raw),
                "kind": "image" if is_image else "file",
            })
            return

        self._send(404, "not found")

    # ---------- DELETE ----------
    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        m = re.match(r"^/chat/api/rooms/([A-Za-z0-9]+)$", path)
        if not m:
            self._send(404, "not found")
            return
        user = self._current_user()
        if not user:
            self._send_json({"ok": False, "detail": "not logged in"}, 401)
            return
        rid = m.group(1)
        room = db_query("SELECT id, kind, title, owner FROM rooms WHERE id=?", (rid,))
        if not room or room[0]["kind"] != "group":
            self._send_json({"ok": False, "detail": "room not found"}, 404)
            return
        if room[0]["owner"] != user["name"]:
            self._send_json({"ok": False, "detail": "only owner can dissolve"}, 403)
            return
        db_exec("DELETE FROM messages WHERE room_id=?", (rid,))
        db_exec("DELETE FROM members WHERE room_id=?", (rid,))
        db_exec("DELETE FROM rooms WHERE id=?", (rid,))
        HUB.broadcast(rid, {"type": "dissolved", "room": rid, "title": room[0]["title"]})
        self._send_json({"ok": True})
        return

    # ---------- WebSocket ----------
    def _handle_ws(self):
        if (self.headers.get("Upgrade") or "").lower() != "websocket":
            self._send(400, "expected websocket")
            return
        key = self.headers.get("Sec-WebSocket-Key")
        if not key:
            self._send(400, "missing key")
            return

        # 鉴权
        cookie = self.headers.get("Cookie") or ""
        user = resolve_user(cookie)
        if not user:
            # 未登录，给个 HTTP 响应然后断开
            body = _json_bytes({"ok": False, "detail": "not logged in"})
            try:
                self.send_response(401)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception:
                pass
            return

        # 握手
        accept = base64.b64encode(
            hashlib.sha1((key + WS_MAGIC).encode()).digest()
        ).decode()
        try:
            self.send_response(101, "Switching Protocols")
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", accept)
            self.end_headers()
        except Exception:
            return

        # 取出原始 socket 并阻塞读
        client = WSClient(self.connection, user["name"])
        joined = set()
        try:
            while True:
                frame = ws_read_frame(self.connection)
                if frame is None:
                    break
                opcode, payload = frame
                if opcode == 0x8:  # close
                    ws_send_close(self.connection)
                    break
                if opcode == 0x9:  # ping
                    ws_send_pong(self.connection, payload)
                    continue
                if opcode == 0xA:  # pong
                    continue
                if opcode != 0x1:  # 只处理文本
                    continue
                try:
                    msg = json.loads(payload.decode("utf-8", "ignore"))
                except Exception:
                    continue
                t = msg.get("type")
                if t == "join":
                    rid = str(msg.get("room") or "")
                    if not rid:
                        continue
                    HUB.join(rid, client)
                    joined.add(rid)
                    client.send_text(json.dumps(
                        {"type": "joined", "room": rid, "online": HUB.online()},
                        ensure_ascii=False,
                    ))
                    HUB.broadcast(rid, {"type": "presence", "online": HUB.online()})
                elif t == "leave":
                    rid = str(msg.get("room") or "")
                    HUB.leave(rid, client)
                    joined.discard(rid)
                elif t == "msg":
                    rid = str(msg.get("room") or "")
                    kind = str(msg.get("kind") or "text")
                    if not rid:
                        continue
                    fname = None
                    if kind in ("image", "file"):
                        # 图片/文件消息：content 只允许是本站在 /chat/uploads/ 下真实存在的文件
                        content = str(msg.get("content") or "").strip()
                        if not re.match(r"^/chat/uploads/[A-Za-z0-9]+\.[A-Za-z0-9]{1,5}$", content):
                            continue
                        ext = os.path.splitext(content)[1].lower()
                        if ext not in ALLOWED_EXTS:
                            continue
                        if (kind == "image") != (ext in IMAGE_EXTS):
                            continue  # kind 与扩展名必须匹配
                        fpath = os.path.join(UPLOAD_DIR, os.path.basename(content))
                        if not os.path.isfile(fpath):
                            continue
                        if len(content) > 200:
                            continue
                        if kind == "file":
                            # 原始文件名（展示/下载用），做安全清洗
                            raw_fn = str(msg.get("fname") or "").strip()
                            raw_fn = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", raw_fn)[:120]
                            if not raw_fn or raw_fn.strip(".") == "":
                                raw_fn = "文件" + ext
                            fname = raw_fn
                    else:
                        kind = "text"
                        content = str(msg.get("content") or "").strip()
                        if not content:
                            continue
                        if len(content) > 4000:
                            content = content[:4000]
                    ts = int(time.time())
                    cur = db_exec(
                        """INSERT INTO messages(room_id, sender, sender_display, sender_avatar, content, kind, fname, created_at)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (rid, user["name"], user["displayName"], user["avatar"], content, kind, fname, ts),
                    )
                    mid = cur.lastrowid
                    HUB.broadcast(rid, {
                        "type": "msg",
                        "room": rid,
                        "id": mid,
                        "sender": user["name"],
                        "sender_display": user["displayName"],
                        "sender_avatar": user["avatar"],
                        "content": content,
                        "kind": kind,
                        "fname": fname,
                        "created_at": ts,
                    })
                elif t == "ping":
                    client.send_text('{"type":"pong"}')
        except Exception as e:
            print(f"[ws] {type(e).__name__}: {e}", flush=True)
        finally:
            for rid in list(joined):
                HUB.leave(rid, client)
            HUB.leave_all(client)
            client.alive = False
            # 通知各房间在线变化
            for rid in list(HUB.rooms.keys()):
                HUB.broadcast(rid, {"type": "presence", "online": HUB.online()})
            try:
                self.connection.close()
            except Exception:
                pass
        # 阻止 BaseHTTPRequestHandler 继续处理这个连接
        self.close_connection = True


# ---------- 启动 ----------

def main():
    server = ThreadingHTTPServer((LISTEN, PORT), Handler)
    server.daemon_threads = True
    print(f"[uc-chat] listening on http://{LISTEN}:{PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
