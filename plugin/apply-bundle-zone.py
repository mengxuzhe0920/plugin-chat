#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 Halo Console/UC 的插件 bundle 建独立 nginx 缓存 zone，便于精准清理。"""
import os
import re
import subprocess
import sys

CONF = "/www/server/panel/vhost/nginx/sams-house.top.conf"

src = open(CONF, encoding="utf-8").read()

if "halo_bundle_cache" in src:
    print("already patched")
    sys.exit(0)

# 备份
bak = CONF + ".bak-zone-20261018"
if not os.path.exists(bak):
    open(bak, "w", encoding="utf-8").write(src)
    print("backup ->", bak)

# 1) 文件头新增独立 zone 定义
old_line = ("proxy_cache_path /www/wwwroot/sams-house.top/proxy_cache_dir "
            "levels=1:2 keys_zone=sams-house_top_cache:20m inactive=30d max_size=5g;")
new_lines = (old_line + "\nproxy_cache_path /www/wwwroot/sams-house.top/bundle_cache_dir "
             "levels=1:2 keys_zone=halo_bundle_cache:10m inactive=7d max_size=1g;")
assert src.count(old_line) == 1, "cache_path line not found"
src = src.replace(old_line, new_lines, 1)

# 2) 仅两个 bundle location 换 zone（/themes/ 等继续用共享 zone）
block_re = re.compile(
    r"(location \^~ /apis/api\.console\.halo\.run/v1alpha1/(?:plugins|ui-plugins)/-/bundle \{.*?)"
    r"\n(\s*)proxy_cache sams-house_top_cache;",
    re.S)
n = 0


def _rep(m):
    global n
    n += 1
    return m.group(1) + "\n" + m.group(2) + "proxy_cache halo_bundle_cache;"


src = block_re.sub(_rep, src)
print("bundle locations switched:", n)
assert n == 2, "expected 2 bundle locations"

open(CONF, "w", encoding="utf-8").write(src)
print("written")

r = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
print("nginx -t rc=%d" % r.returncode)
print((r.stdout + r.stderr).strip())
if r.returncode != 0:
    sys.exit(1)
r = subprocess.run(["systemctl", "reload", "nginx"], capture_output=True, text=True)
print("reload rc=%d %s" % (r.returncode, (r.stdout + r.stderr).strip()))
