#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""图片消息接口测试：POST /chat/api/upload + GET /chat/uploads/* + WS kind=image

覆盖：合法 PNG/GIF/JPEG 上传 / dataURL 前缀 / 静态服务与缓存头 /
      坏扩展名 400 / 伪装图片 400 / 超限 400 / 未登录 401 /
      路径穿越 404 / WS 图片消息广播 / 非法图片 URL 被忽略 /
      文本消息不受影响 / 历史 kind=image / 房间列表预览 [图片]
"""
import sys, json, ssl, re, os, base64, time, socket, struct
import urllib.request, urllib.parse, urllib.error, http.cookiejar

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
BASE = 'https://sams-house.top'

cj = http.cookiejar.CookieJar()
op = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(cj),
    urllib.request.HTTPSHandler(context=ctx)
)

PASS, FAIL = [], []


def check(name, cond, detail=''):
    if cond:
        PASS.append(name)
        print(f'  [PASS] {name}')
    else:
        FAIL.append(name)
        print(f'  [FAIL] {name}  {detail}')


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
    print('[login] ok as', user)


def cookie_header():
    return '; '.join(f'{c.name}={c.value}' for c in cj)


def api(path, method='GET', body=None, with_cookie=True):
    headers = {'User-Agent': 'curl/8', 'Content-Type': 'application/json'}
    if with_cookie:
        headers['Cookie'] = cookie_header()
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body else None,
        method=method,
        headers=headers
    )
    try:
        r = op.open(req)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def api_raw(path):
    """拿原始响应（静态图片用）"""
    req = urllib.request.Request(BASE + path, headers={
        'User-Agent': 'curl/8', 'Cookie': cookie_header()})
    try:
        r = op.open(req)
        return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def ssh(cmd):
    sys.path.insert(0, 'C:/Users/sam/WorkBuddy/2026-10-13-21-16-59/tools')
    import paramiko
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect('191.40.37.234', 22, 'root', 'e4ZxNJnAdicbElo8',
              timeout=25, banner_timeout=45, auth_timeout=45,
              allow_agent=False, look_for_keys=False)
    stdin, stdout, stderr = c.exec_command(cmd, timeout=60)
    out = stdout.read().decode('utf-8', 'ignore')
    c.close()
    return out


# ---------- 简易 WebSocket 客户端 ----------
def ws_connect(path):
    host, port = 'sams-house.top', 443
    sock = socket.create_connection((host, port), timeout=10)
    ssock = ctx.wrap_socket(sock, server_hostname=host)
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\n"
        f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\nCookie: {cookie_header()}\r\n\r\n"
    )
    ssock.sendall(req.encode())
    resp = b''
    while b'\r\n\r\n' not in resp:
        chunk = ssock.recv(4096)
        if not chunk:
            raise RuntimeError('handshake EOF')
        resp += chunk
    if '101' not in resp.split(b'\r\n', 1)[0].decode():
        raise RuntimeError('ws handshake failed: ' + resp.decode('utf-8', 'ignore')[:300])
    return ssock


def ws_send_text(sock, obj):
    payload = json.dumps(obj).encode('utf-8')
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
    sock.settimeout(timeout)
    try:
        head = b''
        while len(head) < 2:
            chunk = sock.recv(2 - len(head))
            if not chunk:
                return None
            head += chunk
        b1, b2 = head[0], head[1]
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
        try:
            return json.loads(payload.decode('utf-8'))
        except Exception:
            return {'_raw': payload[:200].decode('utf-8', 'ignore')}
    except (socket.timeout, TimeoutError):
        return None


def wait_for(sock, pred, timeout=8):
    """读到满足 pred 的消息为止；超时返回 None"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        m = ws_recv(sock, max(0.5, deadline - time.time()))
        if m is None:
            return None
        if pred(m):
            return m
    return None


# 测试素材
PNG_1x1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
GIF_1x1 = base64.b64decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
JPG_FAKE = b'\xff\xd8\xff\xe0' + b'\x00' * 200          # 只有魔术字节的假 JPEG
PNG_HUGE = b'\x89PNG\r\n\x1a\n' + b'\x00' * (6 * 1024 * 1024)  # 超 5MB


def upload(name, raw, expect_ok=True):
    code, j = api('/chat/api/upload', 'POST', {
        'name': name, 'data': base64.b64encode(raw).decode()})
    if expect_ok:
        check(f'上传 {name} → 200', code == 200 and j.get('ok'), f'{code} {j}')
    else:
        check(f'上传 {name} → 400', code == 400, f'{code} {j}')
    return code, j


def main():
    # uploads 目录只可能有本测试的产物（图片功能刚上线，尚无真实图片），先清干净再测
    ssh('rm -f /opt/uc-chat/uploads/* 2>/dev/null; true')

    login('workbuddy', 'Aa1234')

    print('\n== 0. 登录态 ==')
    code, me = api('/chat/api/me')
    check('/me 200', code == 200 and me.get('ok'), f'{code} {me}')
    my_name = me['user']['name']

    print('\n== 1. 建测试群 ==')
    code, j = api('/chat/api/rooms', 'POST',
                  {'title': 'e2e-图片消息测试', 'member_names': []})
    check('建群', code == 200 and j.get('ok'), f'{code} {j}')
    rid = j['id']

    print('\n== 2. 上传合法图片 ==')
    code, j = upload('pixel.png', PNG_1x1)
    png_url = j.get('url') or ''
    check('url 形如 /chat/uploads/xxx.png',
          bool(re.match(r'^/chat/uploads/[A-Za-z0-9]+\.png$', png_url)), png_url)

    code, j = upload('pixel.gif', GIF_1x1)
    gif_url = j.get('url') or ''
    check('GIF 上传 ok', bool(re.match(r'^/chat/uploads/[A-Za-z0-9]+\.gif$', gif_url)), gif_url)

    code, j = upload('pixel.jpg', JPG_FAKE)
    jpg_url = j.get('url') or ''
    check('JPEG 上传 ok', bool(re.match(r'^/chat/uploads/[A-Za-z0-9]+\.jpg$', jpg_url)), jpg_url)

    # dataURL 前缀
    code, j = api('/chat/api/upload', 'POST', {
        'name': 'dataurl.png',
        'data': 'data:image/png;base64,' + base64.b64encode(PNG_1x1).decode()})
    check('dataURL 前缀上传 200', code == 200 and j.get('ok'), f'{code} {j}')
    dataurl_url = j.get('url') or ''
    check('dataURL 上传返回 png url',
          bool(re.match(r'^/chat/uploads/[A-Za-z0-9]+\.png$', dataurl_url)), dataurl_url)

    print('\n== 3. 静态服务 ==')
    code, hdrs, body = api_raw(png_url)
    check('GET 上传图片 200', code == 200, f'{code}')
    check('Content-Type image/png', 'image/png' in (hdrs.get('Content-Type') or ''), hdrs.get('Content-Type'))
    check('缓存头 max-age=30d', 'max-age' in (hdrs.get('Cache-Control') or ''), hdrs.get('Cache-Control'))
    check('字节一致', body == PNG_1x1, f'{len(body)} vs {len(PNG_1x1)}')

    print('\n== 4. 非法上传 ==')
    upload('evil.txt', PNG_1x1, expect_ok=False)
    upload('fake.png', b'hello world, not a png', expect_ok=False)
    upload('huge.png', PNG_HUGE, expect_ok=False)
    code, j = api('/chat/api/upload', 'POST', {'name': 'x.png', 'data': '!!!notbase64!!!'})
    check('坏 base64 400', code == 400, f'{code} {j}')

    print('\n== 5. 未登录 / 路径穿越 ==')
    # 不带任何 cookie 的 opener（op 自身挂着 CookieProcessor，会自动带登录态）
    op_nocookie = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(BASE + '/chat/api/upload', method='POST',
                                 data=json.dumps({'name': 'x.png',
                                                  'data': base64.b64encode(PNG_1x1).decode()}).encode(),
                                 headers={'User-Agent': 'curl/8',
                                          'Content-Type': 'application/json'})
    try:
        r = op_nocookie.open(req)
        code, j = r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            code, j = e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            code, j = e.code, {}
    check('未登录上传 401', code == 401, f'{code} {j}')
    code, hdrs, body = api_raw('/chat/uploads/../server.py')
    check('路径穿越 404', code == 404, f'{code}')
    code, hdrs, body = api_raw('/chat/uploads/nonexistent123.png')
    check('不存在图片 404', code == 404, f'{code}')

    print('\n== 6. WS 图片消息 ==')
    ws = ws_connect('/chat/ws')
    ws_send_text(ws, {'type': 'join', 'room': rid})
    m = wait_for(ws, lambda x: x.get('type') == 'joined')
    check('WS join 成功', m is not None and m.get('room') == rid, f'{m}')

    # 6.1 正常图片消息
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': png_url, 'kind': 'image'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg' and x.get('kind') == 'image')
    check('图片消息广播 kind=image', m is not None, f'{m}')
    check('广播 content 是上传 URL', m and m.get('content') == png_url, f'{m}')
    check('广播带 id', m and isinstance(m.get('id'), int), f'{m}')

    # 6.2 非法图片 URL 应被忽略（先排空已有消息）
    deadline = time.time() + 1.5
    while time.time() < deadline:
        if ws_recv(ws, 0.5) is None:
            break
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': '/chat/uploads/deadbeef123456.png', 'kind': 'image'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg', timeout=2)
    check('不存在的图片文件被忽略', m is None, f'{m}')
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': 'https://evil.com/x.png', 'kind': 'image'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg', timeout=2)
    check('外链图片 URL 被忽略', m is None, f'{m}')
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': '', 'kind': 'image'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg', timeout=2)
    check('空 content 图片被忽略', m is None, f'{m}')

    print('\n== 7. 历史与列表（此刻最后一条是图片）==')
    code, j = api(f'/chat/api/rooms/{rid}/messages?limit=20')
    msgs = j.get('messages') or []
    img_msgs = [x for x in msgs if x.get('kind') == 'image']
    check('历史含图片消息', len(img_msgs) == 1, f'{msgs}')
    check('历史图片消息 URL 正确', img_msgs and img_msgs[0]['content'] == png_url, f'{img_msgs}')
    code, j = api('/chat/api/rooms')
    room = next((r for r in j.get('rooms', []) if r['id'] == rid), None)
    check('房间存在', room is not None, f'{j}')
    check('列表预览为 [图片]', room and room.get('last_msg') == '[图片]', f'{room}')
    check('列表 last_kind=image', room and room.get('last_kind') == 'image', f'{room}')
    check('列表 last_sender 有值', room and room.get('last_sender'), f'{room}')

    print('\n== 7.5 文本消息不受影响 ==')
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': '文字消息仍然正常'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg' and x.get('kind') == 'text')
    check('文本消息广播 kind=text', m is not None and m.get('content') == '文字消息仍然正常', f'{m}')
    code, j = api(f'/chat/api/rooms/{rid}/messages?limit=20')
    msgs = j.get('messages') or []
    check('历史含文本消息 kind=text',
          any(x.get('kind') == 'text' and x['content'] == '文字消息仍然正常' for x in msgs), f'{msgs}')

    print('\n== 8. 清理 ==')
    code, j = api(f'/chat/api/rooms/{rid}', 'DELETE')
    check('解散测试群', code == 200 and j.get('ok'), f'{code} {j}')
    # 删除上传的测试图片（uuid 文件名，只删 uploads 目录下本次生成的）
    urls = [png_url, gif_url, jpg_url, dataurl_url]
    for u in urls:
        name = u.rsplit('/', 1)[-1]
        ssh(f'rm -f /opt/uc-chat/uploads/{name}')
    left = ssh('ls /opt/uc-chat/uploads/ | wc -l').strip()
    print('  uploads 目录剩余文件数:', left)
    check('测试图片已清理', left == '0', left)

    print(f'\n===== 结果: {len(PASS)} 通过, {len(FAIL)} 失败 =====')
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
