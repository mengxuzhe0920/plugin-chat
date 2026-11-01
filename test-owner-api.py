#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""转让群主接口测试：POST /chat/api/rooms/{id}/owner

覆盖：正常转让 / 非群主 403 / 转让后解散权失效 / 转给自己 400 /
      转给非成员 400 / 私聊 404 / 名单徽章易主 / 不存在 404
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
                  {'title': 'e2e-转让群主测试', 'member_names': []})
    check('建群', code == 200 and j.get('ok'), f'{code} {j}')
    rid = j['id']
    code, j = api(f'/chat/api/rooms/{rid}/members', 'POST', {'member_names': ['samm']})
    check('邀请 samm', code == 200 and j.get('added') == ['samm'], f'{code} {j}')

    # 2) 正常转让
    code, j = api(f'/chat/api/rooms/{rid}/owner', 'POST', {'new_owner': 'samm'})
    check('转让给 samm 成功', code == 200 and j.get('owner') == 'samm', f'{code} {j}')
    check('返回新群主显示名', bool(j.get('owner_display')), f'{j}')

    # 3) 旧群主再转让 → 403
    code, j = api(f'/chat/api/rooms/{rid}/owner', 'POST', {'new_owner': 'samm'})
    check('旧群主再转让 403', code == 403, f'{code} {j}')

    # 4) 旧群主解散 → 403（权力已转移）
    code, j = api(f'/chat/api/rooms/{rid}', 'DELETE')
    check('旧群主解散 403', code == 403, f'{code} {j}')

    # 5) 旧群主转给非成员 → 403（先校验身份）
    code, j = api(f'/chat/api/rooms/{rid}/owner', 'POST', {'new_owner': 'ghost-user'})
    check('非群主转给非成员 403', code == 403, f'{code} {j}')

    # 6) 名单徽章易主 + 新群主置顶
    code, j = api(f'/chat/api/rooms/{rid}/members')
    mem = j.get('members') or []
    samm_row = next((m for m in mem if m['name'] == 'samm'), None)
    wb_row = next((m for m in mem if m['name'] == 'workbuddy'), None)
    check('samm 是群主', samm_row and samm_row.get('owner') is True, f'{samm_row}')
    check('workbuddy 不是群主', wb_row and wb_row.get('owner') is False, f'{wb_row}')
    check('新群主置顶', mem and mem[0]['name'] == 'samm', f'{mem}')

    # 7) 改库把群主改回 workbuddy，测剩余分支
    ssh(f"sqlite3 /opt/uc-chat/uc_chat.db \"UPDATE rooms SET owner='workbuddy' WHERE id='{rid}'\"")

    # 8) 转给自己 → 400
    code, j = api(f'/chat/api/rooms/{rid}/owner', 'POST', {'new_owner': 'workbuddy'})
    check('转给自己 400', code == 400, f'{code} {j}')

    # 9) 转给非成员 → 400
    code, j = api(f'/chat/api/rooms/{rid}/owner', 'POST', {'new_owner': 'ghost-user'})
    check('转给非成员 400', code == 400, f'{code} {j}')

    # 10) 缺参数 → 400
    code, j = api(f'/chat/api/rooms/{rid}/owner', 'POST', {})
    check('缺 new_owner 400', code == 400, f'{code} {j}')

    # 11) 私聊转让 → 404
    code, j = api('/chat/api/dm', 'POST', {'peer': 'samm'})
    dm_id = j.get('id')
    code, j = api(f'/chat/api/rooms/{dm_id}/owner', 'POST', {'new_owner': 'samm'})
    check('私聊转让 404', code == 404, f'{code} {j}')

    # 12) 不存在的群 → 404
    code, j = api('/chat/api/rooms/zzzzzzzzzzzz/owner', 'POST', {'new_owner': 'samm'})
    check('不存在房间 404', code == 404, f'{code} {j}')

    # 13) 清理（samm 是群主，workbuddy 无权解散，直接删库）
    ssh(f"sqlite3 /opt/uc-chat/uc_chat.db \"DELETE FROM messages WHERE room_id='{rid}'; DELETE FROM members WHERE room_id='{rid}'; DELETE FROM rooms WHERE id='{rid}'\"")
    out = ssh("python3 -c \"import sqlite3; c=sqlite3.connect('/opt/uc-chat/uc_chat.db'); print([r[0] for r in c.execute('SELECT id FROM rooms')])\"")
    check('测试群已清理', rid not in out, f'rooms={out.strip()}')

    print(f'\n===== 结果: {len(PASS)} 通过, {len(FAIL)} 失败 =====')
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
