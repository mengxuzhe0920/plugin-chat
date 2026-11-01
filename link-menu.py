#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把已创建的菜单项挂到主菜单"""
import base64, http.cookiejar, json, os, re, ssl, sys, time
import urllib.parse, urllib.request

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

BASE = "https://sams-house.top"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
CRED = json.load(open(r"C:\Users\sam\WorkBuddy\2026-10-13-21-16-59\tools\halo-cred.json",
                      encoding="utf-8"))
USER, PW = CRED["user"], CRED["pass"]

ITEM_NAME = "menu-item-zcbh9qsk"
MENU_NAME = "primary"


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

# 拿当前菜单
c, b = call("GET", "/api/v1alpha1/menus/%s" % MENU_NAME)
if c != 200:
    print("[X] GET menu failed", c, b[:300]); sys.exit(1)
menu = json.loads(b)
items = menu["spec"].get("menuItems", [])

if ITEM_NAME in items:
    print("[skip] 已挂到主菜单")
    sys.exit(0)

items.append(ITEM_NAME)
menu["spec"]["menuItems"] = items

c, b = call("PUT", "/api/v1alpha1/menus/%s" % MENU_NAME, menu)
print("[PUT menu] HTTP %s" % c)
if c != 200:
    print(b[:500]); sys.exit(1)
print("[OK] 小窝聊天已加入主菜单")

# 验证
c, b = call("GET", "/apis/api.halo.run/v1alpha1/menus/-")
m = json.loads(b)
for it in m.get("menuItems", []):
    spec = it.get("spec", {})
    print("   -", spec.get("displayName"), "->", spec.get("href"))
