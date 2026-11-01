#!/bin/bash
# 重新预热插件 bundle + 确认真实 theme 资产可访问
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

echo '=== 从首页找真实 theme 资产路径 ==='
HOMEPAGE=$(curl -s "$SITE/")
THEME_ASSET=$(echo "$HOMEPAGE" | grep -oE '/themes/[^"]+\.(css|js)' | head -1)
echo "  asset: $THEME_ASSET"
if [ -n "$THEME_ASSET" ]; then
  curl -s -D - -o /dev/null "$SITE$THEME_ASSET" | grep -iE "^HTTP|cache-control|x-sam-cache" | tr -d '\r'
fi

echo '=== 重新预热插件 bundle（2 次，第 2 次应 HIT） ==='
URL=$(curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/apis/api.console.halo.run/v1alpha1/plugins/-/bundle.js" | grep -i '^location:' | sed 's/location: //I' | tr -d '\r')
for i in 1 2; do
  curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE$URL" | grep -iE "^HTTP|x-sam-bundle-cache" | tr -d '\r' | tr '\n' ' '; echo
done

echo '=== games 目录确认（403 是否既有行为） ==='
ls /www/wwwroot/sams-house.top/games/ 2>/dev/null | head -5
ls /www/wwwroot/sams-house.top/games/index.html 2>/dev/null && echo "has index" || echo "no index.html -> 403 是既有行为，游戏通过直链访问"

rm -f /tmp/pw.txt /tmp/pw.enc /tmp/p.pem /tmp/ck.txt /tmp/l.html
echo done
