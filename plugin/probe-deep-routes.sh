#!/bin/bash
# 确认 /console/* 与 /uc/* 深层路由都返回同一 SPA 外壳，且无 API 混入
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

BASE_HASH=$(curl -s -b /tmp/ck.txt "$SITE/console/" | md5sum | cut -d' ' -f1)
echo "console shell md5: $BASE_HASH"
for P in "/console/posts" "/console/plugins" "/console/anything-deep" "/console" "/uc" "/uc/" "/uc/notifications" "/uc/profile" "/uc/deep/route"; do
  CODE=$(curl -s -b /tmp/ck.txt -o /tmp/p.html -w '%{http_code}' "$SITE$P")
  HASH=$(md5sum /tmp/p.html | cut -d' ' -f1)
  SIZE=$(stat -c%s /tmp/p.html)
  if [ "$HASH" = "$BASE_HASH" ]; then SAME="same-shell"; else SAME="DIFFERENT"; fi
  echo "  $P -> $CODE size=$SIZE $SAME"
done
echo "=== 这些路径的 cache-control ==="
curl -s -b /tmp/ck.txt -D - -o /dev/null "$SITE/uc/" | grep -i cache-control | tr -d '\r'

rm -f /tmp/pw.txt /tmp/pw.enc /tmp/p.pem /tmp/ck.txt /tmp/l.html /tmp/p.html
echo done
