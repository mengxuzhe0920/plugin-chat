#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复上一补丁的两个问题：
1. map 用 $upstream_status -> 改 $status（缓存 HIT 时前者为空，导致 immutable 头丢失）
2. console/uc 正则 location 永不生效（catch-all 是 ^~ /，前缀命中即跳过正则）
   -> 改为 ^~ 前缀 location + 精确 location
"""
import subprocess
import sys

CONF = "/www/server/panel/vhost/nginx/sams-house.top.conf"
src = open(CONF, encoding="utf-8").read()

changed = 0

# ---- 修复 1：map 变量 ----
old_map = 'map "$upstream_status" $sam_ui_cc {'
new_map = 'map "$status" $sam_ui_cc {'
if old_map in src:
    src = src.replace(old_map, new_map, 1)
    changed += 1
    print("fix1: map variable -> $status")

# ---- 修复 2：正则 location -> 前缀 location ----
old_console = """    location ~ ^/console(/|$) {
      proxy_cache sams-house_top_cache;"""
new_console = """    location = /console {
      proxy_cache sams-house_top_cache;"""
if old_console in src:
    src = src.replace(old_console, new_console, 1)
    changed += 1
    print("fix2a: /console -> exact location")

old_console_slash = """    location ~ ^/uc(/|$) {
      proxy_cache sams-house_top_cache;"""
# 上面这个 old_console_slash 实际是 uc 的，先处理 console 的斜杠版
old_console2 = """    location ~ ^/console(/|$) {
      proxy_cache sams-house_top_cache;"""
# 已处理；下面把 console 的斜杠 location 补上（插在 exact 之后）
# 先找 uc 的正则块整体替换
old_uc = """    location ~ ^/uc(/|$) {
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
    }"""
new_uc = """    location = /uc {
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
    location ^~ /console/ {
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
    location ^~ /uc/ {
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
    }"""
if old_uc in src:
    src = src.replace(old_uc, new_uc, 1)
    changed += 1
    print("fix2b: /uc + /console/ -> prefix/exact locations")

assert changed == 3, "expected 3 fixes, got %d" % changed

open(CONF, "w", encoding="utf-8").write(src)
print("written")

r = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
print("nginx -t rc=%d" % r.returncode)
print((r.stdout + r.stderr).strip())
if r.returncode != 0:
    sys.exit(1)
r = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, text=True)
print("reload rc=%d %s" % (r.returncode, (r.stdout + r.stderr).strip()))
