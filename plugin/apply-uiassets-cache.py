#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""UC/Console 加载提速：
1. /ui-assets/ 内容哈希静态资产 -> nginx 缓存 30d + 浏览器 immutable 1y（主因：原来无 ETag+no-cache，每次全量重下 2.5MB）
2. /console /uc SPA 外壳 -> nginx 微缓存 10s（外壳无用户信息，已实测两次请求一致）
3. 404 不套 immutable 头，避免浏览器缓存错误页
"""
import os
import re
import subprocess
import sys

CONF = "/www/server/panel/vhost/nginx/sams-house.top.conf"
MARK = "UI-ASSETS-CACHE"

src = open(CONF, encoding="utf-8").read()

if MARK in src:
    print("already patched")
    sys.exit(0)

bak = CONF + ".bak-uiassets-20261018"
if not os.path.exists(bak):
    open(bak, "w", encoding="utf-8").write(src)
    print("backup ->", bak)

# ---------- 1) http 级：map + 独立缓存 zone ----------
anchor = ("proxy_cache_path /www/wwwroot/sams-house.top/proxy_cache_dir "
          "levels=1:2 keys_zone=sams-house_top_cache:20m inactive=30d max_size=5g;")
assert src.count(anchor) == 1, "cache_path anchor not found"

http_block = anchor + """
# UI 资产缓存策略：200 -> immutable 一年；其余（404 等）-> no-store（WorkBuddy 2026-10-18）
map "$upstream_status" $sam_ui_cc {
    default "no-store";
    200     "public, max-age=31536000, immutable";
}
proxy_cache_path /www/wwwroot/sams-house.top/uiassets_cache_dir levels=1:2 keys_zone=halo_uiassets_cache:2m inactive=60d max_size=3g;"""
src = src.replace(anchor, http_block, 1)

# ---------- 2) /ui-assets/ location ----------
uiassets_loc = """    #UI-ASSETS-CACHE-START (WorkBuddy 2026-10-18)
    # 内容哈希静态资产：长缓存 + immutable，彻底消除每次开 UC 重下 2.5MB
    location ^~ /ui-assets/ {
      proxy_cache halo_uiassets_cache;
      proxy_cache_valid 200 30d;
      proxy_cache_valid 404 1m;
      proxy_ignore_headers Set-Cookie Cache-Control;
      proxy_hide_header Cache-Control;
      add_header Cache-Control $sam_ui_cc always;
      proxy_cache_lock on;
      proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
      proxy_cache_background_update on;
      add_header X-Sam-UIAssets-Cache $upstream_cache_status always;
      proxy_pass http://127.0.0.1:8090;
      proxy_set_header Host $http_host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_http_version 1.1;
      proxy_connect_timeout 60s;
      proxy_read_timeout 120s;
    }
    #UI-ASSETS-CACHE-END
    #CONSOLE-UC-MICROCACHE-START (WorkBuddy 2026-10-18)
    # SPA 外壳（无用户信息，已实测）：nginx 微缓存 10s，浏览器仍 no-cache 保证升级即时生效
    location ~ ^/console(/|$) {
      proxy_cache sams-house_top_cache;
      proxy_cache_valid 200 10s;
      proxy_ignore_headers Set-Cookie;
      proxy_hide_header Cache-Control;
      add_header Cache-Control "no-cache, max-age=0, must-revalidate" always;
      proxy_cache_lock on;
      proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
      proxy_cache_background_update on;
      add_header X-Sam-Shell-Cache $upstream_cache_status always;
      proxy_pass http://127.0.0.1:8090;
      proxy_set_header Host $http_host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_http_version 1.1;
      proxy_connect_timeout 60s;
      proxy_read_timeout 120s;
    }
    location ~ ^/uc(/|$) {
      proxy_cache sams-house_top_cache;
      proxy_cache_valid 200 10s;
      proxy_ignore_headers Set-Cookie;
      proxy_hide_header Cache-Control;
      add_header Cache-Control "no-cache, max-age=0, must-revalidate" always;
      proxy_cache_lock on;
      proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;
      proxy_cache_background_update on;
      add_header X-Sam-Shell-Cache $upstream_cache_status always;
      proxy_pass http://127.0.0.1:8090;
      proxy_set_header Host $http_host;
      proxy_set_header X-Real-IP $remote_addr;
      proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
      proxy_set_header X-Forwarded-Proto $scheme;
      proxy_http_version 1.1;
      proxy_connect_timeout 60s;
      proxy_read_timeout 120s;
    }
    #CONSOLE-UC-MICROCACHE-END

    location ^~ / {"""

old_catchall = "    location ^~ / {"
assert src.count(old_catchall) == 1, "catch-all anchor not found"
src = src.replace(old_catchall, uiassets_loc, 1)

open(CONF, "w", encoding="utf-8").write(src)
print("written")

r = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
print("nginx -t rc=%d" % r.returncode)
print((r.stdout + r.stderr).strip())
if r.returncode != 0:
    sys.exit(1)
r = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, text=True)
print("reload rc=%d %s" % (r.returncode, (r.stdout + r.stderr).strip()))
