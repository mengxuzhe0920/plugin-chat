#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本地 uc-chat/static/index.html 推到服务器 /opt/uc-chat/static/index.html（改前备份）。"""
import os
import paramiko

HOST, USER, PW = "191.40.37.234", "root", "e4ZxNJnAdicbElo8"
LOCAL = r"C:/Users/sam/WorkBuddy/2026-10-18-13-17-35/uc-chat/static/index.html"
REMOTE = "/opt/uc-chat/static/index.html"

SHELL = """set -e
cp {remote} {remote}.bak-exit-$(date +%Y%m%d-%H%M%S)
ls -la {remote} {remote}.bak-exit-* | tail -3
echo '--- 语法自检（grep 关键节点）---'
grep -c 'btn-exit' {remote}
grep -c 'exit-pop' {remote}
systemctl restart uc-chat
sleep 1
systemctl is-active uc-chat
curl -s -o /dev/null -w 'local /chat/ -> %{{http_code}}\\n' http://127.0.0.1:8322/
""".format(remote=REMOTE)


def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PW, timeout=30,
              allow_agent=False, look_for_keys=False)
    sftp = c.open_sftp()
    sftp.put(LOCAL, REMOTE)
    st = sftp.stat(REMOTE)
    print("[put] %s -> %s bytes" % (REMOTE, st.st_size))
    sftp.close()
    _in, out, err = c.exec_command(SHELL, timeout=120)
    print(out.read().decode("utf-8", "ignore"))
    e = err.read().decode("utf-8", "ignore")
    if e.strip():
        print("STDERR:", e[:800])
    c.close()


if __name__ == "__main__":
    main()
