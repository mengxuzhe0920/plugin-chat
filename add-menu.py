#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在主菜单加「小窝聊天」入口"""
import base64, http.cookiejar, json, os, re, ssl, sys, time
import urllib.parse, urllib.request

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

BASE = "https://sams-house.top"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
CRED = json.load(open(r"C:\Users\sam\WorkBuddy\2026-10-13-21-16-59\tools\halo-cred.json",
                      encoding="utf-8"))
USER, PW = CRED["user"], CRED["pass"]


class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def login():
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),
                                     urllib.request.HTTPSHandler(context=CTX))
    op.addheaders = [("User-Agent", "Mozilla/5.0"), ("Accept", "application/json")]
    h = op.open(urllib.request.Request(BASE + "/login"), timeout=90).read().decode("utf-8", "ignore")
    csrf = re.search(r'name="_csrf"\s+value="([^"]+)"', h).group(1)
    pub = load_der_public_key(base64.b64decode(
        re.search(r'const\s+publicKey\s*=\s*"([^"]+)"', h).group(1).replace("\\/", "/")))
    enc = base64.b64encode(pub.encrypt(PW.encode(), padding.PKCS1v15())).decode()
    rq = urllib.request.Request(BASE + "/login", data=urllib.parse.urlencode(
        {"_csrf": csrf, "username": USER, "password": enc, "remember-me": "true"}).encode())
    rq.add_header("Content-Type", "application/x-www-form-urlencoded")
    pr = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar),
                                     urllib.request.HTTPSHandler(context=CTX), NR())
    try:
        loc = pr.open(rq, timeout=90).headers.get("Location", "")
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location", "") or ""
    if "error" in (loc or ""):
        raise RuntimeError("登录被拒: " + loc)
    xsrf = next((c.value for c in jar if c.name == "XSRF-TOKEN"), "")
    return op, jar, xsrf


def make_call(op, xsrf_box):
    def call(method, path, body=None, tries=4, timeout=60):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        last = ""
        for n in range(tries):
            try:
                r = urllib.request.Request(BASE + path, data=data, method=method)
                if data is not None:
                    r.add_header("Content-Type", "application/json")
                    r.add_header("X-XSRF-TOKEN", xsrf_box[0])
                    r.add_header("Origin", BASE)
                    r.add_header("Referer", BASE + "/console/")
                resp = op.open(r, timeout=timeout)
                return resp.getcode(), resp.read().decode("utf-8", "ignore")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "ignore")
            except Exception as e:
                last = "ERR:%s" % type(e).__name__
                if n == tries - 1:
                    return 0, last
                time.sleep(3)
        return 0, last
    return call


op = None
for attempt in range(6):
    try:
        op, jar, xsrf = login()
        break
    except Exception as e:
        print("[登录] 第 %d 次失败：%s，等 40s" % (attempt + 1, e))
        time.sleep(40)
if op is None:
    raise SystemExit("[X] 多次登录失败")
xsrf_box = [xsrf]
call = make_call(op, xsrf_box)

# 拿主菜单结构
c, b = call("GET", "/apis/api.halo.run/v1alpha1/menus/-")
print("[menu] HTTP %s" % c)
if c != 200:
    print(b[:500]); sys.exit(1)

menu = json.loads(b)
items = menu.get("menuItems", [])

# 检查是否已存在
for it in items:
    spec = it.get("spec", {})
    if spec.get("href") == "/chat/" or spec.get("displayName") == "小窝聊天":
        print("[skip] 已存在小窝聊天菜单项 name=%s" % it["metadata"]["name"])
        sys.exit(0)

# 创建菜单项
icon = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><path fill="#3a3a36" d="M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2m0 14H5.2L4 17.2V4h16z"/></svg>'
payload = {
    "apiVersion": "v1alpha1",
    "kind": "MenuItem",
    "metadata": {
        "generateName": "menu-item-",
        "annotations": {"icon": icon}
    },
    "spec": {
        "displayName": "小窝聊天",
        "href": "/chat/",
        "priority": 5,
        "target": "_self",
        "children": []
    }
}
c, b = call("POST", "/api/v1alpha1/menuitems", payload)
print("[create menuitem] HTTP %s" % c)
if c not in (200, 201):
    print(b[:500]); sys.exit(1)
new_item = json.loads(b)
new_name = new_item["metadata"]["name"]
print("   name=%s" % new_name)

# 把它挂到主菜单
# 先看主菜单资源
c, b = call("GET", "/apis/api.halo.run/v1alpha1/menus/-")
menu = json.loads(b)
# 找菜单 name（通常 metadata.name）
menu_meta_name = menu.get("metadata", {}).get("name")
if not menu_meta_name:
    # 通过另一个端点拿
    c, b = call("GET", "/apis/api.console.halo.run/v1alpha1/menus")
    print("[menus list] HTTP %s" % c)
    if c == 200:
        for m in json.loads(b).get("items", []):
            print("   menu:", m["metadata"]["name"], m["spec"].get("displayName"))
            if m["spec"].get("displayName") in ("主菜单", "Primary", "primary"):
                menu_meta_name = m["metadata"]["name"]

print("menu name:", menu_meta_name)

# 直接 PUT menuitems 的 parent 关系比较麻烦。Halo 的做法是菜单项挂在 menu 的 spec.menuItems 数组
c, b = call("GET", "/api/v1alpha1/menus/%s" % (menu_meta_name or "primary"))
print("[menu detail] HTTP %s" % c)
if c != 200:
    print(b[:500]); sys.exit(1)
menu_obj = json.loads(b)
print("menu keys:", list(menu_obj.keys()))
print("menu.spec keys:", list((menu_obj.get("spec") or {}).keys()))
print("menu.spec:", json.dumps(menu_obj.get("spec"), ensure_ascii=False)[:500])
