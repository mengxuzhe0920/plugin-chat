#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用便携 JDK 编译插件类（含 stub）到 build/classes。"""
import os
import subprocess
import sys
import glob

BASE = os.path.dirname(os.path.abspath(__file__))
JDK_DIR = r"C:\Users\sam\.workbuddy\binaries\java"


def find_javac():
    # 找解压后的 jdk-21*/bin/javac.exe
    for cand in glob.glob(os.path.join(JDK_DIR, "jdk-*", "bin", "javac.exe")):
        return cand
    for cand in glob.glob(os.path.join(JDK_DIR, "**", "javac.exe"), recursive=True):
        return cand
    return None


def main():
    javac = find_javac()
    if not javac:
        sys.exit("找不到 javac，请先解压 JDK 到 " + JDK_DIR)
    print("javac =", javac)

    out = os.path.join(BASE, "build", "classes")
    os.makedirs(out, exist_ok=True)

    sources = []
    for sub in ("stub", os.path.join("src", "main", "java")):
        root = os.path.join(BASE, sub)
        for dirpath, _d, filenames in os.walk(root):
            for fn in filenames:
                if fn.endswith(".java"):
                    sources.append(os.path.join(dirpath, fn))
    print("sources:")
    for s in sources:
        print("  ", os.path.relpath(s, BASE))

    cmd = [javac, "-encoding", "utf-8", "-d", out, "-nowarn"] + sources
    print("\nrunning javac...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout)
    if r.stderr:
        print(r.stderr, file=sys.stderr)
    if r.returncode != 0:
        sys.exit("javac failed: %d" % r.returncode)
    print("\n[OK] classes ->", out)


if __name__ == "__main__":
    main()
