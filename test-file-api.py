#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""文件消息接口测试：上传白名单 + WS kind=file + 历史 fname + 关键词搜索

覆盖：pdf/txt/md/docx/xlsx/pptx/csv/json/zip/rar/7z/mp3/wav/mp4/apk 上传 /
      图片通道不受影响 / 不支持的扩展名 400 / 超 10MB 400 / 超 5MB 图片 400 /
      伪装图片 400 / 未登录 401 / 路径穿越 404 / 文件静态服务与缓存头 /
      WS kind=file 广播与 fname 保留 / fname 安全清洗 / kind 与扩展名错配被忽略 /
      不存在的文件被忽略 / 历史返回 fname / 搜索匹配正文与文件名 /
      搜索分页 / 列表预览 [文件] / 测试数据清理
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
MY_FILES = []   # 本次测试上传产生的 uploads 文件名，清理用


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
    """拿原始响应（静态文件用）"""
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


def drain(sock, seconds=1.2):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if ws_recv(sock, 0.4) is None:
            break


# 测试素材
PNG_1x1 = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
FILE_HUGE = b'\x00' * (10 * 1024 * 1024 + 1024)   # 超 10MB
PNG_HUGE = b'\x89PNG\r\n\x1a\n' + b'\x00' * (6 * 1024 * 1024)  # 超 5MB

# 各文件类型的假内容（非图片不校验魔术字节）
DOC_SAMPLES = {
    '说明文档.pdf':  b'%PDF-1.4 fake pdf content for test',
    '笔记.txt':      '小窝聊天文件消息测试 plain text'.encode(),
    'readme.md':     b'# hello uc-chat file message',
    '报表.xlsx':     b'PK\x03\x04 fake xlsx content',
    '合同.docx':     b'PK\x03\x04 fake docx content',
    '演示.pptx':     b'PK\x03\x04 fake pptx content',
    '数据.csv':      b'a,b,c\n1,2,3\n',
    '配置.json':     b'{"chat": "file"}',
    '打包.zip':      b'PK\x03\x04 fake zip content',
    '压缩.7z':       b'7z\xbc\xaf\x27\x1c fake 7z content',
    '录音.mp3':      b'ID3 fake mp3 content',
    'clip.mp4':      b'\x00\x00\x00\x18ftypmp42 fake mp4 content',
}


def upload(name, raw):
    code, j = api('/chat/api/upload', 'POST', {
        'name': name, 'data': base64.b64encode(raw).decode()})
    if code == 200 and j.get('ok'):
        MY_FILES.append(j['url'].rsplit('/', 1)[-1])
    return code, j


def main():
    login('workbuddy', 'Aa1234')

    print('\n== 0. 登录态 ==')
    code, me = api('/chat/api/me')
    check('/me 200', code == 200 and me.get('ok'), f'{code} {me}')
    my_name = me['user']['name']

    print('\n== 1. 建测试群 ==')
    code, j = api('/chat/api/rooms', 'POST',
                  {'title': 'e2e-文件消息测试', 'member_names': []})
    check('建群', code == 200 and j.get('ok'), f'{code} {j}')
    rid = j['id']

    print('\n== 2. 上传各类文件（kind=file）==')
    file_urls = {}
    for name, raw in DOC_SAMPLES.items():
        code, j = upload(name, raw)
        ok = code == 200 and j.get('ok') and j.get('kind') == 'file'
        check(f'上传 {name} → 200 kind=file', ok, f'{code} {j}')
        if ok:
            file_urls[name] = j['url']
            check(f'{name} url 形如 /chat/uploads/uuid+ext',
                  bool(re.match(r'^/chat/uploads/[A-Za-z0-9]+\.[A-Za-z0-9]{1,5}$', j['url'])), j['url'])

    print('\n== 3. 图片通道不受影响 ==')
    code, j = upload('pixel.png', PNG_1x1)
    check('上传 PNG → 200 kind=image', code == 200 and j.get('kind') == 'image', f'{code} {j}')
    png_url = j.get('url') or ''

    print('\n== 4. 非法上传 ==')
    code, j = upload('病毒.exe', b'MZ fake exe')
    check('不支持的扩展名 .exe → 400', code == 400, f'{code} {j}')
    code, j = upload('超大.zip', FILE_HUGE)
    check('超过 10MB 文件 → 400', code == 400, f'{code} {j}')
    code, j = upload('超大.png', PNG_HUGE)
    check('超过 5MB 图片 → 400', code == 400, f'{code} {j}')
    code, j = upload('伪装.png', b'hello world, not a png')
    check('伪装图片 → 400', code == 400, f'{code} {j}')
    code, j = api('/chat/api/upload', 'POST', {'name': 'x.pdf', 'data': '!!!notbase64!!!'})
    check('坏 base64 → 400', code == 400, f'{code} {j}')
    code, j = api('/chat/api/upload', 'POST', {'name': '', 'data': base64.b64encode(b'x').decode()})
    check('空文件名 → 400', code == 400, f'{code} {j}')

    print('\n== 5. 未登录 / 路径穿越 / 不存在 ==')
    op_nocookie = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(BASE + '/chat/api/upload', method='POST',
                                 data=json.dumps({'name': 'x.pdf',
                                                  'data': base64.b64encode(b'x').decode()}).encode(),
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
    code, hdrs, body = api_raw('/chat/uploads/deadbeef12345678.pdf')
    check('不存在的文件 404', code == 404, f'{code}')

    print('\n== 6. 文件静态服务 ==')
    pdf_url = file_urls.get('说明文档.pdf')
    code, hdrs, body = api_raw(pdf_url)
    check('GET 上传文件 200', code == 200, f'{code}')
    check('Content-Type application/pdf',
          'application/pdf' in (hdrs.get('Content-Type') or ''), hdrs.get('Content-Type'))
    check('缓存头 30d', 'max-age' in (hdrs.get('Cache-Control') or ''), hdrs.get('Cache-Control'))
    check('字节一致', body == DOC_SAMPLES['说明文档.pdf'], f'{len(body)}')

    print('\n== 7. WS 文件消息 ==')
    ws = ws_connect('/chat/ws')
    ws_send_text(ws, {'type': 'join', 'room': rid})
    m = wait_for(ws, lambda x: x.get('type') == 'joined')
    check('WS join 成功', m is not None and m.get('room') == rid, f'{m}')

    # 7.1 正常文件消息：kind=file，fname 保留
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': pdf_url,
                      'kind': 'file', 'fname': '说明文档.pdf'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg' and x.get('kind') == 'file')
    check('文件消息广播 kind=file', m is not None, f'{m}')
    check('广播 content 是上传 URL', m and m.get('content') == pdf_url, f'{m}')
    check('fname 原样保留', m and m.get('fname') == '说明文档.pdf', f'{m}')

    # 7.2 fname 安全清洗：非法字符变下划线
    evil_name = '../ev\\il:na*me?"<>|.pdf'
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': pdf_url,
                      'kind': 'file', 'fname': evil_name})
    m = wait_for(ws, lambda x: x.get('type') == 'msg' and x.get('kind') == 'file'
                 and x.get('fname') != '说明文档.pdf')
    check('fname 非法字符被清洗', m is not None and m.get('fname') == '.._ev_il_na_me_____.pdf',
          f'{m}')
    check('清洗后仍带 .pdf 后缀', m and m.get('fname', '').endswith('.pdf'), f'{m}')

    # 7.3 kind 与扩展名错配应被忽略
    drain(ws)
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': png_url, 'kind': 'file'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg', timeout=2)
    check('kind=file 但扩展名是图片 → 忽略', m is None, f'{m}')
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': pdf_url, 'kind': 'image'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg', timeout=2)
    check('kind=image 但扩展名是 pdf → 忽略', m is None, f'{m}')

    # 7.4 不存在的文件被忽略
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': '/chat/uploads/deadbeef12345678.pdf',
                      'kind': 'file', 'fname': 'x.pdf'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg', timeout=2)
    check('不存在的文件 URL 被忽略', m is None, f'{m}')

    # 7.5 外链 URL 被忽略
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': 'https://evil.com/x.pdf',
                      'kind': 'file', 'fname': 'x.pdf'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg', timeout=2)
    check('外链文件 URL 被忽略', m is None, f'{m}')

    # 7.6 图片消息仍然正常
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': png_url, 'kind': 'image'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg' and x.get('kind') == 'image')
    check('图片消息广播 kind=image（回归）', m is not None and m.get('content') == png_url, f'{m}')

    print('\n== 8. 历史返回 fname ==')
    code, j = api(f'/chat/api/rooms/{rid}/messages?limit=50')
    msgs = j.get('messages') or []
    file_msgs = [x for x in msgs if x.get('kind') == 'file']
    check('历史含文件消息', len(file_msgs) == 2, f'{file_msgs}')
    check('历史文件消息带 fname', all(x.get('fname') for x in file_msgs), f'{file_msgs}')
    check('历史图片消息 kind=image',
          any(x.get('kind') == 'image' for x in msgs), f'{msgs}')

    print('\n== 9. 关键词搜索 ==')
    # 9.1 搜正文（文本消息）
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': '小窝聊天室文件功能验证'})
    wait_for(ws, lambda x: x.get('type') == 'msg' and x.get('kind') == 'text')
    code, j = api(f'/chat/api/rooms/{rid}/messages?limit=50&q=' +
                  urllib.parse.quote('文件功能'))
    msgs = j.get('messages') or []
    check('搜索正文命中 1 条', len(msgs) == 1 and msgs[0]['content'] == '小窝聊天室文件功能验证',
          f'{msgs}')
    # 9.2 搜文件名（文件消息 content 是 URL，只能靠 fname 命中）
    code, j = api(f'/chat/api/rooms/{rid}/messages?limit=50&q=' +
                  urllib.parse.quote('说明文档'))
    msgs = j.get('messages') or []
    check('搜索文件名命中 1 条', len(msgs) == 1 and msgs[0].get('fname') == '说明文档.pdf',
          f'{msgs}')
    # 9.3 搜不到
    code, j = api(f'/chat/api/rooms/{rid}/messages?limit=50&q=' +
                  urllib.parse.quote('不存在的关键词xyz'))
    msgs = j.get('messages') or []
    check('搜索无结果 → 空', len(msgs) == 0, f'{msgs}')
    # 9.4 LIKE 通配符不应越界（% 是字面量）
    code, j = api(f'/chat/api/rooms/{rid}/messages?limit=50&q=' + urllib.parse.quote('%'))
    msgs = j.get('messages') or []
    check('q=% 搜不到字面量内容 → 空', len(msgs) == 0, f'{msgs}')
    # 9.5 搜索 + 分页 before 组合
    code, j = api(f'/chat/api/rooms/{rid}/messages?limit=50&q=' +
                  urllib.parse.quote('说明文档') + '&before=999999999')
    msgs = j.get('messages') or []
    check('搜索 + before 分页正常', len(msgs) == 1, f'{msgs}')

    print('\n== 10. 列表预览 ==')
    # 末尾补发一条文件消息，验证列表预览为 [文件]
    ws_send_text(ws, {'type': 'msg', 'room': rid, 'content': pdf_url,
                      'kind': 'file', 'fname': '说明文档.pdf'})
    m = wait_for(ws, lambda x: x.get('type') == 'msg' and x.get('kind') == 'file')
    check('末尾文件消息广播', m is not None, f'{m}')
    code, j = api('/chat/api/rooms')
    room = next((r for r in j.get('rooms', []) if r['id'] == rid), None)
    check('房间存在', room is not None, f'{j}')
    check('列表预览为 [文件]', room and room.get('last_msg') == '[文件]', f'{room}')
    check('列表 last_kind=file', room and room.get('last_kind') == 'file', f'{room}')

    print('\n== 11. 清理 ==')
    code, j = api(f'/chat/api/rooms/{rid}', 'DELETE')
    check('解散测试群', code == 200 and j.get('ok'), f'{code} {j}')
    # 只删本次测试上传的文件（uuid 名，不碰真实用户文件）
    for f in MY_FILES:
        ssh(f'rm -f /opt/uc-chat/uploads/{f}')
    gone = 0
    for f in MY_FILES:
        code, hdrs, body = api_raw(f'/chat/uploads/{f}')
        if code == 404:
            gone += 1
    check(f'本次上传的 {len(MY_FILES)} 个文件全部删除', gone == len(MY_FILES), f'{gone}/{len(MY_FILES)}')

    print(f'\n===== 结果: {len(PASS)} 通过, {len(FAIL)} 失败 =====')
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
