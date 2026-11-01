#!/bin/bash
# 对比 gzip / identity 下大资产的耗时，确认瓶颈
U=https://sams-house.top/ui-assets/editor/editor.29a22067.js
echo "=== headers (gzip) ==="
curl -s -D - -o /dev/null -H "Accept-Encoding: gzip" "$U" | grep -iE "content-encoding|content-length|content-type|cache-control|^HTTP" | tr -d "\r"
echo "=== headers (identity) ==="
curl -s -D - -o /dev/null -H "Accept-Encoding: identity" "$U" | grep -iE "content-encoding|content-length|content-type|cache-control|^HTTP" | tr -d "\r"
echo "=== timing gzip x3 ==="
for i in 1 2 3; do curl -s -o /dev/null -H "Accept-Encoding: gzip" -w "  t=%{time_total}s dl=%{size_download}B\n" "$U"; done
echo "=== timing identity x3 ==="
for i in 1 2 3; do curl -s -o /dev/null -H "Accept-Encoding: identity" -w "  t=%{time_total}s dl=%{size_download}B\n" "$U"; done
echo "=== 小文件对照 (console-CDLHJvpk.js 36KB) ==="
curl -s -o /dev/null -H "Accept-Encoding: gzip" -w "  gzip t=%{time_total}s dl=%{size_download}B\n" "https://sams-house.top/ui-assets/console-CDLHJvpk.js"
curl -s -o /dev/null -H "Accept-Encoding: identity" -w "  iden t=%{time_total}s dl=%{size_download}B\n" "https://sams-house.top/ui-assets/console-CDLHJvpk.js"
