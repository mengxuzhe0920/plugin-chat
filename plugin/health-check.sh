#!/bin/bash
# 全站健康检查：确认缓存改动没有破坏任何页面
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

echo '=== 公开页面 ==='
for P in "/" "/archives" "/archives/uc-chat-launch" "/chat/" "/chat/api/health" "/games/" "/login"; do
  R=$(curl -s -o /dev/null -w "%{http_code} t=%{time_total}s size=%{size_download}" "$SITE$P")
  echo "  $P -> $R"
done

echo '=== 登录态页面 ==='
for P in "/console/" "/uc/" "/apis/api.console.halo.run/v1alpha1/users/-"; do
  R=$(curl -s -b /tmp/ck.txt -o /dev/null -w "%{http_code} t=%{time_total}s" "$SITE$P")
  echo "  $P -> $R"
done

echo '=== 插件 bundle（独立 zone 仍工作） ==='
URL=$(curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE/apis/api.console.halo.run/v1alpha1/plugins/-/bundle.js" | grep -i '^location:' | sed 's/location: //I' | tr -d '\r')
curl -s -D - -o /dev/null -b /tmp/ck.txt "$SITE$URL" | grep -iE "^HTTP|x-sam-bundle-cache" | tr -d '\r'

echo '=== themes 缓存（共享 zone 未受影响） ==='
curl -s -o /dev/null -D - "$SITE/themes/ethereal/assets/css/style.css" 2>/dev/null | grep -iE "^HTTP|x-sam-cache" | tr -d '\r' | head -4
T=$(curl -s -o /dev/null -w "%{http_code}" "$SITE/themes/ethereal/")
echo "  themes index -> $T"

echo '=== nginx 错误日志（最近 5 条） ==='
tail -5 /www/wwwlogs/nginx/error.log 2>/dev/null || tail -5 /var/log/nginx/error.log 2>/dev/null || echo '(no error log)'

rm -f /tmp/pw.txt /tmp/pw.enc /tmp/p.pem /tmp/ck.txt /tmp/l.html
echo done
