#!/bin/bash
# 验证 ui-assets 缓存头 + 预热全部资产 + 计时对比
SITE=https://sams-house.top
PW='Aa1234'

curl -s -c /tmp/ck.txt "$SITE/login" -o /tmp/l.html
PUB=$(grep -o 'const publicKey = "[^"]*"' /tmp/l.html | sed 's/const publicKey = "//;s/"$//')
{ echo '-----BEGIN PUBLIC KEY-----'; printf '%s\n' "$PUB" | sed 's/\\\//\//g'; echo '-----END PUBLIC KEY-----'; } > /tmp/p.pem
printf '%s' "$PW" > /tmp/pw.txt
openssl pkeyutl -encrypt -pubin -inkey /tmp/p.pem -pkeyopt rsa_padding_mode:pkcs1 -in /tmp/pw.txt -out /tmp/pw.enc
ENC=$(base64 -w0 /tmp/pw.enc)
CSRF=$(grep -o 'name="_csrf" value="[^"]*"' /tmp/l.html | sed 's/name="_csrf" value="//;s/"$//')
curl -s -o /dev/null -b /tmp/ck.txt -c /tmp/ck.txt -X POST "$SITE/login" \
  --data-urlencode "_csrf=$CSRF" --data-urlencode "username=workbuddy" --data-urlencode "password=$ENC"

echo '=== 1. 已知资产响应头 ==='
curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/ui-assets/editor/editor.29a22067.js" | grep -iE "^HTTP|cache-control|x-sam-uiassets" | tr -d '\r'

echo '=== 2. 404 不带 immutable ==='
curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/ui-assets/__nope__.js" | grep -iE "^HTTP|cache-control|x-sam-uiassets" | tr -d '\r'

echo '=== 3. /uc/ 外壳微缓存 ==='
for i in 1 2; do
  curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/uc/" | grep -iE "^HTTP|x-sam-shell|cache-control" | tr -d '\r' | tr '\n' ' '; echo
done

echo '=== 4. 预热全部资产（console + uc html 引用） ==='
ASSETS=$(curl -s -b /tmp/ck.txt "$SITE/console/" | grep -oE '/ui-assets/[^"]+\.(js|css|ico|woff2?|png|svg)' | sort -u)
ASSETS="$ASSETS $(curl -s -b /tmp/ck.txt "$SITE/uc/" | grep -oE '/ui-assets/[^"]+\.(js|css|ico|woff2?|png|svg)' | sort -u)"
ASSETS=$(echo "$ASSETS" | sort -u)
N=0; BYTES=0
for U in $ASSETS; do
  S=$(curl -s -b /tmp/ck.txt -o /dev/null -w '%{size_download}' "$SITE$U")
  BYTES=$((BYTES + S)); N=$((N + 1))
done
echo "预热 $N 个资产，共 $((BYTES / 1024)) KB（未压缩）"

echo '=== 5. 预热后再测（应全部 HIT 且带 immutable） ==='
curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/ui-assets/editor/editor.29a22067.js" | grep -iE "^HTTP|cache-control|x-sam-uiassets" | tr -d '\r'
curl -s -o /dev/null -b /tmp/ck.txt -H "Accept-Encoding: gzip" -w "  editor gzip t=%{time_total}s dl=%{size_download}B\n" "$SITE/ui-assets/editor/editor.29a22067.js"
curl -s -o /dev/null -b /tmp/ck.txt -H "Accept-Encoding: gzip" -w "  api-client gzip t=%{time_total}s dl=%{size_download}B\n" "$SITE/ui-assets/api-client/api-client.02ea3dd6.js"
curl -s -o /dev/null -b /tmp/ck.txt -H "Accept-Encoding: gzip" -w "  console js t=%{time_total}s dl=%{size_download}B\n" "$SITE/ui-assets/console-CDLHJvpk.js"

echo '=== 6. 缓存目录 ==='
find /www/wwwroot/sams-house.top/uiassets_cache_dir -type f | wc -l
du -sh /www/wwwroot/sams-house.top/uiassets_cache_dir

rm -f /tmp/pw.txt /tmp/pw.enc /tmp/p.pem /tmp/ck.txt /tmp/l.html
echo done
