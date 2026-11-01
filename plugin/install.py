#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上传并安装 PluginChat 到 Halo，然后启用。"""
import base64, http.cookiejar, json, os, re, ssl, sys, time
import urllib.parse, urllib.request, uuid

from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_der_public_key

BASE = "https://sams-house.top"
CTX = ssl.create_default_context(); CTX.check_hostname = False; CTX.verify_mode = ssl.CERT_NONE
CRED = json.load(open(r"C:\Users\sam\WorkBuddy\2026-10-13-21-16-59\tools\halo-cred.json",
                      encoding="utf-8"))
USER, PW = CRED["user"], CRED["pass"]
JAR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist", "PluginChat-0.1.0.jar")
PLUGIN_NAME = "PluginChat"


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
    return op, xsrf


def make_call(op, xsrf_box):
    def call(method, path, body=None, raw=None, ctype="application/json", tries=4, timeout=120):
        data = raw if raw is not None else (
            json.dumps(body).encode("utf-8") if body is not None else None)
        last = ""
        for n in range(tries):
            try:
                r = urllib.request.Request(BASE + path, data=data, method=method)
                if data is not None and ctype:
                    r.add_header("Content-Type", ctype)
                if data is not None:
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
        op, xsrf = login()
        break
    except Exception as e:
        print("[登录] 第 %d 次失败：%s，等 40s" % (attempt + 1, e))
        time.sleep(40)
if op is None:
    raise SystemExit("[X] 登录失败")
xsrf_box = [xsrf]
call = make_call(op, xsrf_box)

# 若已存在，先删旧插件
c, b = call("GET", "/apis/plugin.halo.run/v1alpha1/plugins/%s" % PLUGIN_NAME)
if c == 200:
    print("[已存在] 先停用并删除旧版")
    call("PUT", "/apis/api.console.halo.run/v1alpha1/plugins/%s/plugin-state" % PLUGIN_NAME,
         {"enable": False})
    time.sleep(2)
    c2, b2 = call("DELETE", "/apis/plugin.halo.run/v1alpha1/plugins/%s" % PLUGIN_NAME)
    print("   delete HTTP %s" % c2)
    time.sleep(3)

# 上传安装
data = open(JAR, "rb").read()
boundary = "----WBPlugin" + uuid.uuid4().hex
body = ("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"PluginChat-0.1.0.jar\"\r\n"
        "Content-Type: application/java-archive\r\n\r\n" % boundary).encode() + data + \
       ("\r\n--%s--\r\n" % boundary).encode()
c, b = call("POST", "/apis/api.console.halo.run/v1alpha1/plugins/install",
            raw=body, ctype="multipart/form-data; boundary=%s" % boundary, timeout=180)
print("[install] HTTP %s" % c)
print("   %s" % b[:400])
if c not in (200, 201):
    sys.exit(1)

# 启用
time.sleep(2)
c, b = call("PUT", "/apis/api.console.halo.run/v1alpha1/plugins/%s/plugin-state" % PLUGIN_NAME,
            {"enable": True})
print("[enable] HTTP %s" % c)

# 查状态
time.sleep(3)
c, b = call("GET", "/apis/plugin.halo.run/v1alpha1/plugins/%s" % PLUGIN_NAME)
if c == 200:
    p = json.loads(b)
    print("[status] enabled=%s phase=%s" % (
        p.get("spec", {}).get("enabled"),
        (p.get("status") or {}).get("phase")))
    print("[done] 插件已安装。请到 Console → 插件 查看「小窝聊天」。")
else:
    print("[warn] 查询插件失败 HTTP %s: %s" % (c, b[:200]))


# 清理 nginx 的 bundle 缓存（防止同版本重装后拿到旧 bundle）
# bundle 有独立 zone：/www/wwwroot/sams-house.top/bundle_cache_dir，只清它，不动 themes 缓存
def purge_bundle_cache():
    try:
        import paramiko
    except ImportError:
        print("[cache] 无 paramiko，跳过清理（插件 ?v= hash 变化会自动失效，一般无需手动清）")
        return
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect("191.40.37.234", 22, "root", "e4ZxNJnAdicbElo8",
                    timeout=25, banner_timeout=45, auth_timeout=45,
                    allow_agent=False, look_for_keys=False)
        cmd = ("find /www/wwwroot/sams-house.top/bundle_cache_dir -type f -delete 2>/dev/null; "
               "echo cleared; ls /www/wwwroot/sams-house.top/bundle_cache_dir 2>/dev/null | wc -l")
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=60)
        out = stdout.read().decode("utf-8", "ignore").strip().splitlines()
        print("[cache] bundle 缓存已清理：%s" % (out[0] if out else "?"))
    except Exception as e:
        print("[cache] 清理失败（不影响插件安装）：%s: %s" % (type(e).__name__, e))
    finally:
        ssh.close()


purge_bundle_cache()
