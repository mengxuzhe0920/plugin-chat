#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""发布「小窝聊天室上线了」公告帖。纯文字，无附件无封面。"""
import base64, http.cookiejar, json, os, re, ssl, sys, time
import urllib.parse, urllib.request

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

BASE = "https://sams-house.top"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
CRED = json.load(open(r"C:\Users\sam\WorkBuddy\2026-10-13-21-16-59\tools\halo-cred.json",
                      encoding="utf-8"))
USER, PW = CRED["user"], CRED["pass"]

BODY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "post-body.html")
TITLE = "小窝聊天室上线了"
SLUG = "uc-chat-launch"
EXCERPT = "站点自带了一个能说话的地方——群聊、私聊、实时推送，用小窝账号直接进。"
TAGS = ["站点更新"]


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
    def call(method, path, body=None, raw=None, ctype="application/json",
             tries=4, timeout=120, auth=True):
        data = raw if raw is not None else (
            json.dumps(body).encode("utf-8") if body is not None else None)
        last = ""
        for n in range(tries):
            try:
                r = urllib.request.Request(BASE + path, data=data, method=method)
                if data is not None and ctype:
                    r.add_header("Content-Type", ctype)
                if auth and data is not None:
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


# 登录
op = None
for attempt in range(6):
    try:
        op, jar, xsrf = login()
        break
    except Exception as e:
        print("[登录] 第 %d 次失败：%s，等待 40s" % (attempt + 1, e))
        time.sleep(40)
if op is None:
    raise SystemExit("[X] 多次登录失败")
xsrf_box = [xsrf]
call = make_call(op, xsrf_box)

c, b = call("GET", "/apis/api.console.halo.run/v1alpha1/users/-")
me = json.loads(b)["user"]
if me["metadata"]["name"] == "anonymousUser":
    raise SystemExit("[X] 登录未生效")
print("[OK] 已登录 %s" % me["metadata"]["name"])

# 检查 slug 是否已存在
c, b = call("GET", "/apis/api.console.halo.run/v1alpha1/posts?size=200")
if c == 200:
    for p in json.loads(b).get("items", []):
        if p.get("spec", {}).get("slug") == SLUG and not p.get("spec", {}).get("deleted"):
            print("[!] slug 已存在：%s，直接返回" % p["metadata"]["name"])
            print("permalink=%s" % (p.get("status", {}) or {}).get("permalink"))
            sys.exit(0)

body = open(BODY_FILE, encoding="utf-8").read()

payload = {
    "post": {
        "apiVersion": "content.halo.run/v1alpha1",
        "kind": "Post",
        "metadata": {"generateName": "post-"},
        "spec": {
            "title": TITLE, "slug": SLUG, "template": "", "cover": "",
            "deleted": False, "publish": False, "pinned": False,
            "allowComment": True, "visible": "PUBLIC", "priority": 0, "owner": USER,
            "excerpt": {"autoGenerate": False, "raw": EXCERPT},
            "categories": [], "tags": TAGS, "htmlMetas": [],
        },
    },
    "content": {"raw": body, "content": body, "rawType": "HTML"},
    "categories": [], "tags": TAGS,
}

c, b = call("POST", "/apis/api.console.halo.run/v1alpha1/posts", payload)
print("[创建] HTTP %s" % c)
if c not in (200, 201):
    payload["post"]["spec"]["tags"] = []
    payload["tags"] = []
    c, b = call("POST", "/apis/api.console.halo.run/v1alpha1/posts", payload)
    print("[创建·无标签] HTTP %s" % c)
    if c not in (200, 201):
        print(b[:800]); sys.exit(1)

d = json.loads(b)
name = d["metadata"]["name"]
print("   name=%s slug=%s" % (name, d["spec"].get("slug")))

# 发布
c, b = call("PUT", "/apis/api.console.halo.run/v1alpha1/posts/%s/publish" % name)
print("[发布] HTTP %s" % c)
time.sleep(2)
c, b = call("GET", "/apis/api.console.halo.run/v1alpha1/posts/%s" % name)
permalink = (json.loads(b).get("status", {}) or {}).get("permalink")
print("   permalink=%s" % permalink)

# 线上验证
if permalink:
    req = urllib.request.Request(BASE + permalink, headers={"User-Agent": "curl/8"})
    r = op.open(req, timeout=30)
    html = r.read().decode("utf-8", "ignore")
    ok = "小窝聊天室" in html and "/uc" in html
    print("[线上验证] HTTP %s, contains title & /uc: %s" % (r.status, ok))
