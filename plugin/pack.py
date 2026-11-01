#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把编译产物打成 Halo 插件 jar。

jar 布局（Halo 2.x 插件约定）：
  plugin.yaml                 插件描述
  run/halo/chat/*.class       插件入口类
  org/pf4j/*.class            （不打 stub，运行时用 Halo 自带的）
  console/main.js             UI provider（IIFE）
  console/style.css           可选

用法：python pack.py
产物：dist/PluginChat-0.1.0.jar
"""
import os
import sys
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
CLASSES = os.path.join(BASE, "build", "classes")
CONSOLE = os.path.join(BASE, "src", "main", "resources", "console")
PLUGIN_YAML = os.path.join(BASE, "plugin.yaml")
OUT_DIR = os.path.join(BASE, "dist")
OUT = os.path.join(OUT_DIR, "PluginChat-0.1.0.jar")


def add_tree(zf, root, prefix=""):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            arc = prefix + rel
            zf.write(full, arc)
            print("  +", arc)


def main():
    if not os.path.isfile(PLUGIN_YAML):
        sys.exit("plugin.yaml 不存在")
    if not os.path.isdir(CLASSES):
        sys.exit("build/classes 不存在，先运行 javac 编译（见 build.py）")

    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.isfile(OUT):
        os.remove(OUT)

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        # plugin.yaml 以 src/main/resources 下的为准（与构建工具读取的一致）
        yaml_src = os.path.join(BASE, "src", "main", "resources", "plugin.yaml")
        if not os.path.isfile(yaml_src):
            yaml_src = PLUGIN_YAML
        zf.write(yaml_src, "plugin.yaml")
        print("  + plugin.yaml")
        for dirpath, _d, filenames in os.walk(CLASSES):
            for fn in filenames:
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, CLASSES).replace(os.sep, "/")
                # 剔除 stub：org/pf4j/* 和 run/halo/app/*
                if rel.startswith("org/pf4j/") or rel.startswith("run/halo/app/"):
                    continue
                zf.write(full, rel)
                print("  +", rel)
        if os.path.isdir(CONSOLE):
            for dirpath, _d, filenames in os.walk(CONSOLE):
                for fn in filenames:
                    full = os.path.join(dirpath, fn)
                    rel = os.path.relpath(full, CONSOLE).replace(os.sep, "/")
                    zf.write(full, "console/" + rel)
                    print("  + console/" + rel)

    size = os.path.getsize(OUT)
    print("\n[OK] %s (%d bytes)" % (OUT, size))


if __name__ == "__main__":
    main()
