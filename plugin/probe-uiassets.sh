#!/bin/bash
# 确认 /ui-assets/ 是纯静态：404 行为、ETag、随机路径探测
B=https://sams-house.top/ui-assets
echo "=== 不存在的文件 ==="
curl -s -D - -o /dev/null "$B/__no_such_file__.js" | grep -iE "^HTTP|content-type|content-length" | tr -d "\r"
echo "=== 目录路径 ==="
curl -s -D - -o /dev/null "$B/" | grep -iE "^HTTP|content-type" | tr -d "\r"
echo "=== 已知文件的 ETag/Last-Modified ==="
curl -s -D - -o /dev/null "$B/console-CDLHJvpk.js" | grep -iE "^HTTP|etag|last-modified|cache-control" | tr -d "\r"
echo "=== 多次请求 ETag 是否稳定 ==="
for i in 1 2; do curl -s -D - -o /dev/null "$B/console-CDLHJvpk.js" | grep -i etag | tr -d "\r"; done
echo "=== 条件请求（If-None-Match）是否 304 ==="
ET=$(curl -s -D - -o /dev/null "$B/console-CDLHJvpk.js" | grep -i etag | sed 's/etag: //I' | tr -d '\r')
echo "etag=$ET"
curl -s -D - -o /dev/null -H "If-None-Match: $ET" "$B/console-CDLHJvpk.js" | grep -iE "^HTTP" | tr -d "\r"
echo "=== 文件数估算：console html 里引用的 asset 数 ==="
curl -s "https://sams-house.top/console/" | grep -oE '/ui-assets/[^"]+' | sort -u | wc -l
