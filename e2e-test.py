#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""端到端测试：登录 → /me → 建群 → WebSocket → 发消息 → 收消息"""
import sys, os, json, ssl, re, time, socket, base64, struct, hashlib
import urllib.request, urllib.parse, urllib.error, http.cookiejar

sys.path.insert(0, 'C:/Users/sam/WorkBuddy/2026-10-13-21-16-59/tools')

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
BASE = 'https://sams-house.top'

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    urllib.request.HTTPSHandler(context=ctx)
)


def login(user, passwd):
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.serialization import load_der_public_key
    r = op.open(urllib.request.Request(BASE + '/login', headers={'User-Agent': 'curl/8'}))
    html = r.read().decode('utf-8', 'ignore')
    token = re.search(r'name="_csrf"\s+value="([^"]+)"', html).group(1)
    pub_b64 = re.search(r'const\s+publicKey\s*=\s*"([^"]+)"', html).group(1).replace('\\/', '/')
    key = load_der_public_key(base64.b64decode(pub_b64))
    enc = base64.b64encode(key.encrypt(passwd.encode(), padding.PKCS1v15())).decode()
    data = urllib.parse.urlencode({
        '_csrf': token, 'username': user, 'password': enc, 'remember-me': 'true'
    }).encode()
    req = urllib.request.Request(BASE + '/login', data=data, headers={
        'User-Agent': 'curl/8', 'Content-Type': 'application/x-www-form-urlencoded'
    })
    # 禁止自动重定向，判断 Location
    class NR(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    op2 = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cj),
        urllib.request.HTTPSHandler(context=ctx), NR())
    try:
        r = op2.open(req)
        loc = r.headers.get('Location', '')
    except urllib.error.HTTPError as e:
        loc = e.headers.get('Location', '') or ''
    if 'error' in loc:
        raise RuntimeError('login failed: ' + loc)
    print('[login] ok')


def cookie_header():
    return '; '.join(f'{c.name}={c.value}' for c in cj)


def api(path, method='GET', body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body else None,
        method=method,
        headers={
            'User-Agent': 'curl/8',
            'Cookie': cookie_header(),
            'Content-Type': 'application/json',
        }
    )
    try:
        r = op.open(req)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or '{}')


def ws_connect(path):
    """简易 WebSocket 客户端（wss）"""
    host = 'sams-house.top'
    port = 443
    sock = socket.create_connection((host, port), timeout=10)
    ssock = ctx.wrap_socket(sock, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"Cookie: {cookie_header()}\r\n"
        f"\r\n"
    )
    ssock.sendall(req.encode())
    # 读握手响应头
    resp = b''
    while b'\r\n\r\n' not in resp:
        chunk = ssock.recv(4096)
        if not chunk:
            raise RuntimeError('handshake EOF')
        resp += chunk
    status_line = resp.split(b'\r\n', 1)[0].decode()
    print('[ws] handshake:', status_line)
    if '101' not in status_line:
        raise RuntimeError('ws handshake failed: ' + resp.decode('utf-8', 'ignore')[:500])
    return ssock


def ws_send_text(sock, text):
    payload = text.encode('utf-8')
    mask = os.urandom(4)
    header = bytearray([0x81])
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack('>H', n))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack('>Q', n))
    header.extend(mask)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(bytes(header) + masked)


def ws_recv(sock, timeout=5):
    """读一帧，返回 (opcode, payload)；超时返回 None"""
    sock.settimeout(timeout)
    try:
        head = b''
        while len(head) < 2:
            chunk = sock.recv(2 - len(head))
            if not chunk:
                return None
            head += chunk
        b1, b2 = head[0], head[1]
        opcode = b1 & 0x0F
        plen = b2 & 0x7F
        if plen == 126:
            plen = struct.unpack('>H', sock.recv(2))[0]
        elif plen == 127:
            plen = struct.unpack('>Q', sock.recv(8))[0]
        payload = b''
        while len(payload) < plen:
            chunk = sock.recv(min(65536, plen - len(payload)))
            if not chunk:
                return None
            payload += chunk
        return opcode, payload
    except socket.timeout:
        return None


# ---------- 测试 ----------
login('workbuddy', 'Aa1234')

print('\n== 1. /chat/api/me ==')
code, j = api('/chat/api/me')
print(code, j)
assert code == 200 and j['user']['name'] == 'workbuddy', 'me failed'

print('\n== 2. 建群 ==')
code, j = api('/chat/api/rooms', 'POST', {'title': 'UC 测试群·自动验收', 'member_names': []})
print(code, j)
assert code == 200
room_id = j['id']

print('\n== 3. 房间列表 ==')
code, j = api('/chat/api/rooms')
print(code, f'{len(j.get("rooms", []))} rooms')
assert code == 200
assert any(r['id'] == room_id for r in j['rooms'])

print('\n== 4. WebSocket 连接 ==')
ws = ws_connect('/chat/ws')

print('\n== 5. join 房间 ==')
ws_send_text(ws, json.dumps({'type': 'join', 'room': room_id}))
f = ws_recv(ws, timeout=5)
assert f, 'no joined reply'
op_, pl = f
msg = json.loads(pl.decode())
print('joined:', msg)
assert msg['type'] == 'joined'
# 可能再收到 presence 广播
f2 = ws_recv(ws, timeout=2)
if f2:
    print('extra:', json.loads(f2[1].decode()))

print('\n== 6. 发消息 ==')
ws_send_text(ws, json.dumps({'type': 'msg', 'room': room_id, 'content': 'hello UC 聊天'}))
f = ws_recv(ws, timeout=5)
assert f, 'no msg echo'
msg = json.loads(f[1].decode())
print('recv:', msg)
assert msg['type'] == 'msg' and msg['content'] == 'hello UC 聊天'
assert msg['sender'] == 'workbuddy'

print('\n== 7. 历史消息 ==')
code, j = api(f'/chat/api/rooms/{room_id}/messages')
print(code, f'{len(j.get("messages", []))} messages')
assert code == 200
assert any(m['content'] == 'hello UC 聊天' for m in j['messages'])

print('\n== 8. 用户列表 ==')
code, j = api('/chat/api/users')
print(code, f'{len(j.get("users", []))} users, online={j.get("online")}')
assert code == 200

ws.close()
print('\n[ALL OK]')
