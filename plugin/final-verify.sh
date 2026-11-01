#!/bin/bash
# 最终验证：immutable 头（HIT 时也要有）、shell 微缓存、404 no-store、计时
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

echo '=== A. ui-assets HIT 时应带 immutable（关键修复） ==='
for i in 1 2; do
  echo "--- req$i ---"
  curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/ui-assets/editor/editor.29a22067.js" | grep -iE "^HTTP|cache-control|x-sam-uiassets" | tr -d '\r'
done

echo '=== B. 404 应 no-store ==='
curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/ui-assets/__nope__.js" | grep -iE "^HTTP|cache-control" | tr -d '\r'

echo '=== C. /uc/ 与 /console/ 外壳微缓存 ==='
for P in "/uc/" "/console/" "/uc" "/console" "/uc/profile" "/console/posts"; do
  R=$(curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE$P" | grep -iE "^HTTP|x-sam-shell-cache" | tr -d '\r' | tr '\n' ' ')
  echo "  $P -> $R"
done

echo '=== D. 计时（gzip） ==='
curl -s -o /dev/null -b /tmp/ck.txt -H "Accept-Encoding: gzip" -w "  editor(1.16MB) t=%{time_total}s dl=%{size_download}B\n" "$SITE/ui-assets/editor/editor.29a22067.js"
curl -s -o /dev/null -b /tmp/ck.txt -H "Accept-Encoding: gzip" -w "  api-client(537KB) t=%{time_total}s dl=%{size_download}B\n" "$SITE/ui-assets/api-client/api-client.02ea3dd6.js"
curl -s -o /dev/null -b /tmp/ck.txt -w "  uc shell t=%{time_total}s dl=%{size_download}B\n" "$SITE/uc/"

echo '=== E. 全资产二次命中统计 ==='
ASSETS=$(curl -s -b /tmp/ck.txt "$SITE/console/" | grep -oE '/ui-assets/[^"]+\.(js|css|ico|woff2?|png|svg)' | sort -u)
HIT=0; MISS=0
for U in $ASSETS; do
  S=$(curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE$U" | grep -i "x-sam-uiassets-cache" | grep -c "HIT")
  if [ "$S" = "1" ]; then HIT=$((HIT+1)); else MISS=$((MISS+1)); fi
done
echo "  HIT=$HIT MISS=$MISS"

rm -f /tmp/pw.txt /tmp/pw.enc /tmp/p.pem /tmp/ck.txt /tmp/l.html
echo done
