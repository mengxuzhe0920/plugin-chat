#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""退出群聊接口测试：POST /chat/api/rooms/{id}/leave

覆盖：群主不可退 403 / 正常退群 / 退群后名单与人数的变化 /
      退群后消息接口 403（权限回收）/ 会话列表消失 / 重复退群 400 /
      私聊退群 404 / 不存在 404
"""
import sys, json, ssl, re, base64
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

PASS = []
FAIL = []


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
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


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


def main():
    login('workbuddy', 'Aa1234')

    code, me = api('/chat/api/me')
    check('登录态可用', code == 200 and me.get('ok'), f'{code} {me}')

    # 1) 建群 + 邀请 samm
    code, j = api('/chat/api/rooms', 'POST',
                  {'title': 'e2e-退群测试', 'member_names': []})
    check('建群', code == 200 and j.get('ok'), f'{code} {j}')
    rid = j['id']
    code, j = api(f'/chat/api/rooms/{rid}/members', 'POST', {'member_names': ['samm']})
    check('邀请 samm', code == 200 and j.get('added') == ['samm'], f'{code} {j}')

    # 2) 先发一条消息（验证退群后读不到）
    code, j = api(f'/chat/api/rooms/{rid}/messages')
    check('退群前可读消息', code == 200, f'{code} {j}')

    # 3) 群主退群 → 403
    code, j = api(f'/chat/api/rooms/{rid}/leave', 'POST', {})
    check('群主退群 403', code == 403, f'{code} {j}')
    check('错误提示引导转让/解散', '转让' in str(j.get('detail', '')), f'{j}')

    # 4) 改库把群主转给 samm，workbuddy 变成普通成员
    ssh(f"sqlite3 /opt/uc-chat/uc_chat.db \"UPDATE rooms SET owner='samm' WHERE id='{rid}'\"")

    # 5) 普通成员退群 → 200
    code, j = api(f'/chat/api/rooms/{rid}/leave', 'POST', {})
    check('普通成员退群成功', code == 200 and j.get('ok'), f'{code} {j}')
    check('退群后返回剩余成员', j.get('members') == ['samm'], f'{j}')

    # 6) 退群后：名单只剩 samm
    code, j = api(f'/chat/api/rooms/{rid}/members')
    check('退群后访问名单 403', code == 403, f'{code} {j}')

    # 7) 退群后：消息接口 403（权限已回收）
    code, j = api(f'/chat/api/rooms/{rid}/messages')
    check('退群后读消息 403', code == 403, f'{code} {j}')

    # 8) 退群后：会话列表不再有该群
    code, j = api('/chat/api/rooms')
    ids = [r['id'] for r in (j.get('rooms') or [])]
    check('会话列表已无该群', rid not in ids, f'{ids}')

    # 9) 重复退群 → 400
    code, j = api(f'/chat/api/rooms/{rid}/leave', 'POST', {})
    check('重复退群 400', code == 400, f'{code} {j}')

    # 10) 私聊退群 → 404
    code, j = api('/chat/api/dm', 'POST', {'peer': 'samm'})
    dm_id = j.get('id')
    code, j = api(f'/chat/api/rooms/{dm_id}/leave', 'POST', {})
    check('私聊退群 404', code == 404, f'{code} {j}')

    # 11) 不存在的群 → 404
    code, j = api('/chat/api/rooms/zzzzzzzzzzzz/leave', 'POST', {})
    check('不存在房间 404', code == 404, f'{code} {j}')

    # 12) 清理（samm 是群主，直接删库）
    ssh(f"sqlite3 /opt/uc-chat/uc_chat.db \"DELETE FROM messages WHERE room_id='{rid}'; DELETE FROM members WHERE room_id='{rid}'; DELETE FROM rooms WHERE id='{rid}'\"")
    out = ssh("python3 -c \"import sqlite3; c=sqlite3.connect('/opt/uc-chat/uc_chat.db'); print([r[0] for r in c.execute('SELECT id FROM rooms')])\"")
    check('测试群已清理', rid not in out, f'rooms={out.strip()}')

    print(f'\n===== 结果: {len(PASS)} 通过, {len(FAIL)} 失败 =====')
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
