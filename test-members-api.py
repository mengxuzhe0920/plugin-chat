#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""群成员名单接口测试：GET /chat/api/rooms/{id}/members

覆盖：群主标识 / 自己标识 / 在线字段 / 群主置顶排序 / 非成员 403 /
      解散后 404 / 不存在 404 / 私聊成员可见 / DM 无群主标识
"""
import sys, json, ssl, re, base64, time
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
    """在服务器上执行命令（改库用）"""
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

    # 0) 登录态
    code, me = api('/chat/api/me')
    check('登录态可用 /me', code == 200 and me.get('ok'), f'{code} {me}')
    my_name = me['user']['name']

    # 1) 建群（只有我自己）
    code, j = api('/chat/api/rooms', 'POST',
                  {'title': 'e2e-成员名单测试', 'member_names': []})
    check('建群', code == 200 and j.get('ok'), f'{code} {j}')
    rid = j['id']

    # 2) 成员名单：1 人，我是群主
    code, j = api(f'/chat/api/rooms/{rid}/members')
    check('群成员名单 200', code == 200 and j.get('ok'), f'{code} {j}')
    mem = j.get('members') or []
    check('初始 1 名成员', len(mem) == 1, f'{mem}')
    if mem:
        m0 = mem[0]
        check('我是群主', m0.get('owner') is True, f'{m0}')
        check('「我」标识', m0.get('me') is True, f'{m0}')
        check('有显示名与头像字段', 'display_name' in m0 and 'avatar' in m0, f'{m0}')
        check('有在线字段', 'online' in m0, f'{m0}')
        check('标题正确', j.get('title') == 'e2e-成员名单测试', f'{j.get("title")}')
        check('owner 字段正确', j.get('owner') == my_name, f'{j.get("owner")}')

    # 3) 邀请 samm 后再看名单
    code, j = api(f'/chat/api/rooms/{rid}/members', 'POST', {'member_names': ['samm']})
    check('邀请 samm', code == 200 and j.get('added') == ['samm'], f'{code} {j}')
    code, j = api(f'/chat/api/rooms/{rid}/members')
    mem = j.get('members') or []
    check('邀请后 2 名成员', len(mem) == 2, f'{mem}')
    check('群主置顶（第一项是群主）',
          mem and mem[0].get('owner') is True and mem[0].get('me') is True, f'{mem}')
    samm_row = next((m for m in mem if m['name'] == 'samm'), None)
    check('samm 不是群主', samm_row and samm_row.get('owner') is False, f'{samm_row}')
    check('samm 的「我」标识为 false', samm_row and samm_row.get('me') is False, f'{samm_row}')

    # 4) 非成员访问 → 403（改库把 workbuddy 移出群，再访问）
    ssh(f'sqlite3 /opt/uc-chat/uc_chat.db "DELETE FROM members WHERE room_id=\'{rid}\' AND username=\'workbuddy\'"')
    code, j = api(f'/chat/api/rooms/{rid}/members')
    check('非成员访问 403', code == 403, f'{code} {j}')
    ssh(f'sqlite3 /opt/uc-chat/uc_chat.db "INSERT OR IGNORE INTO members(room_id, username, joined_at) VALUES(\'{rid}\',\'workbuddy\',1)"')
    code, j = api(f'/chat/api/rooms/{rid}/members')
    check('恢复成员后 200', code == 200, f'{code} {j}')

    # 5) 不存在的房间 → 404
    code, j = api('/chat/api/rooms/zzzzzzzzzzzz/members')
    check('不存在房间 404', code == 404, f'{code} {j}')

    # 6) 私聊成员名单：两人可见，无群主标识
    code, j = api('/chat/api/dm', 'POST', {'peer': 'samm'})
    check('发起私聊', code == 200 and j.get('ok'), f'{code} {j}')
    dm_id = j.get('id')
    code, j = api(f'/chat/api/rooms/{dm_id}/members')
    dm_mem = j.get('members') or []
    check('私聊名单 200', code == 200 and j.get('ok'), f'{code} {j}')
    check('私聊 2 名成员', len(dm_mem) == 2, f'{dm_mem}')
    check('私聊无群主标识', all(m.get('owner') is False for m in dm_mem), f'{dm_mem}')
    check('私聊 owner 字段为空', not j.get('owner'), f'{j.get("owner")}')

    # 7) 解散后 → 404
    code, j = api(f'/chat/api/rooms/{rid}', 'DELETE')
    check('解散群', code == 200 and j.get('ok'), f'{code} {j}')
    code, j = api(f'/chat/api/rooms/{rid}/members')
    check('解散后名单 404', code == 404, f'{code} {j}')

    print(f'\n===== 结果: {len(PASS)} 通过, {len(FAIL)} 失败 =====')
    if FAIL:
        sys.exit(1)


if __name__ == '__main__':
    main()
