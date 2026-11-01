#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""群管理功能测试：建群 → 邀请成员 → 解散群 → 权限校验"""
import sys, os, json, ssl, re, base64
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

    # 0) 确保 workbuddy 已注册进 users（/me 会写入）
    code, me = api('/chat/api/me')
    check('登录态可用 /me', code == 200 and me.get('ok'), f'{code} {me}')
    my_name = me['user']['name']

    # 1) 建群
    code, j = api('/chat/api/rooms', 'POST', {'title': 'e2e-群管测试', 'member_names': []})
    check('建群', code == 200 and j.get('ok'), f'{code} {j}')
    rid = j['id']

    # 2) 邀请 samm（真实用户）
    code, j = api(f'/chat/api/rooms/{rid}/members', 'POST', {'member_names': ['samm']})
    check('邀请 samm 成功', code == 200 and j.get('added') == ['samm'], f'{code} {j}')

    # 3) 邀请不存在的人 → 应被跳过
    code, j = api(f'/chat/api/rooms/{rid}/members', 'POST', {'member_names': ['ghost-user-xyz']})
    check('邀请不存在的人被跳过', code == 200 and j.get('added') == [], f'{code} {j}')

    # 4) 重复邀请 → 不重复添加
    code, j = api(f'/chat/api/rooms/{rid}/members', 'POST', {'member_names': ['samm']})
    check('重复邀请不重复添加', code == 200 and j.get('added') == [], f'{code} {j}')

    # 5) 成员列表正确
    code, rooms = api('/chat/api/rooms')
    room = next((r for r in rooms.get('rooms', []) if r['id'] == rid), None)
    check('房间列表含新群且成员数=2',
          room is not None and set(room['members']) == {my_name, 'samm'},
          json.dumps(room, ensure_ascii=False))
    check('owner 是建群人', room and room.get('owner') == my_name)

    # 6) 非群主不能解散：把 owner 改成 samm，再试
    ssh(f"python3 -c \"import sqlite3; c=sqlite3.connect('/opt/uc-chat/uc_chat.db'); "
        f"c.execute(\\\"UPDATE rooms SET owner='samm' WHERE id='{rid}'\\\"); c.commit()\"")
    code, j = api(f'/chat/api/rooms/{rid}', 'DELETE')
    check('非群主解散被拒(403)', code == 403, f'{code} {j}')

    # 7) 恢复 owner 后解散成功
    ssh(f"python3 -c \"import sqlite3; c=sqlite3.connect('/opt/uc-chat/uc_chat.db'); "
        f"c.execute(\\\"UPDATE rooms SET owner='{my_name}' WHERE id='{rid}'\\\"); c.commit()\"")
    code, j = api(f'/chat/api/rooms/{rid}', 'DELETE')
    check('群主解散成功', code == 200 and j.get('ok'), f'{code} {j}')

    # 8) 解散后房间消失、消息接口 404
    code, rooms = api('/chat/api/rooms')
    gone = all(r['id'] != rid for r in rooms.get('rooms', []))
    check('解散后会话列表无该群', gone)
    code, j = api(f'/chat/api/rooms/{rid}/messages')
    check('解散后消息接口 404', code == 404, f'{code} {j}')

    # 9) 邀请接口要求是成员：建个只有自己的群……这里换个角度——
    #    不存在的房间邀请 → 404
    code, j = api('/chat/api/rooms/nosuchroom/members', 'POST', {'member_names': ['samm']})
    check('邀请进不存在的群 404', code == 404, f'{code} {j}')

    print()
    print(f'===== 结果: {len(PASS)} 通过, {len(FAIL)} 失败 =====')
    if FAIL:
        print('失败项:', FAIL)
        sys.exit(1)


if __name__ == '__main__':
    main()
