#!/bin/bash
# bundle 缓存复测 v2：登录 -> 取版本化 URL -> 3 次请求看缓存头 -> 计时 -> 内容校验
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
echo "login done"

URL=$(curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/apis/api.console.halo.run/v1alpha1/plugins/-/bundle.js" | grep -i '^location:' | sed 's/location: //I' | tr -d '\r')
echo "versioned URL: $URL"
[ -z "$URL" ] && { echo 'FAIL: no location header'; exit 1; }

echo '--- 3 次请求（看缓存头） ---'
for i in 1 2 3; do
  H=$(curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE$URL")
  C=$(printf '%s' "$H" | grep -i 'x-sam-bundle-cache' | tr -d '\r')
  L=$(printf '%s' "$H" | grep -i 'content-length' | tr -d '\r')
  echo "req$i: $(printf '%s' "$H" | head -1 | tr -d '\r') | $C | $L"
done

echo '--- 计时 ---'
for i in 1 2 3; do
  curl -s -o /dev/null -b /tmp/ck.txt -w "  t=%{time_total}s size=%{size_download} speed=%{speed_download}B/s\n" "$SITE$URL"
done

echo '--- 内容校验 ---'
curl -s -b /tmp/ck.txt "$SITE$URL" -o /tmp/b.js
echo "小窝聊天 hits: $(grep -c '小窝聊天' /tmp/b.js)"
echo "SamHouseChat hits: $(grep -c 'SamHouseChat' /tmp/b.js)"
echo "size: $(stat -c%s /tmp/b.js) bytes"

echo '--- 缓存目录 ---'
ls -la /usr/local/nginx/proxy_cache_dir/ 2>/dev/null || ls -la /www/server/nginx/proxy_cache_dir/ 2>/dev/null || echo '(cache dir not in usual paths)'

rm -f /tmp/pw.txt /tmp/pw.enc /tmp/p.pem /tmp/ck.txt /tmp/l.html /tmp/b.js
echo 'done'
