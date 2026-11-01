#!/bin/bash
# 复测 bundle 缓存：服务器本地登录 Halo，带 cookie 请求 bundle.js，验证 X-Sam-Bundle-Cache
set -u
SITE=https://sams-house.top
PW='Aa1234'   # halo 超管 workbuddy 的密码（仅在本脚本内存中使用）

echo '=== 1. 取登录页 publicKey ==='
curl -s -c /tmp/halo-login-cookie.txt "$SITE/login" -o /tmp/halo-login.html
PUB=$(grep -o 'const publicKey = "[^"]*"' /tmp/halo-login.html | sed 's/const publicKey = "//;s/"$//')
if [ -z "$PUB" ]; then echo 'FAIL: 未取到 publicKey'; exit 1; fi
# publicKey 是裸 base64 SPKI（无 PEM 头），斜杠是字面 \/，手动包 PEM
{ echo '-----BEGIN PUBLIC KEY-----'; printf '%s\n' "$PUB" | sed 's/\\\//\//g'; echo '-----END PUBLIC KEY-----'; } > /tmp/halo-pub.pem
openssl pkey -pubin -in /tmp/halo-pub.pem -noout 2>&1 | head -2

echo '=== 2. RSA 加密密码 ==='
printf '%s' "$PW" > /tmp/halo-pw.txt
openssl pkeyutl -encrypt -pubin -inkey /tmp/halo-pub.pem \
  -pkeyopt rsa_padding_mode:pkcs1 -in /tmp/halo-pw.txt -out /tmp/halo-pw.enc 2>/tmp/halo-openssl.err
if [ ! -s /tmp/halo-pw.enc ]; then echo "FAIL: openssl 加密失败: $(cat /tmp/halo-openssl.err)"; exit 1; fi
ENC=$(base64 -w0 /tmp/halo-pw.enc)
echo "encrypted (first 24): ${ENC:0:24}..."

echo '=== 3. 登录（不能带 -L） ==='
CSRF=$(grep -o 'name="_csrf" value="[^"]*"' /tmp/halo-login.html | sed 's/name="_csrf" value="//;s/"$//')
echo "csrf field present: $([ -n "$CSRF" ] && echo yes || echo no)"
LOGIN_CODE=$(curl -s -o /tmp/halo-login-resp.html -w '%{http_code}' \
  -b /tmp/halo-login-cookie.txt -c /tmp/halo-login-cookie.txt \
  -X POST "$SITE/login" \
  --data-urlencode "_csrf=$CSRF" \
  --data-urlencode "username=workbuddy" \
  --data-urlencode "password=$ENC")
echo "login http=$LOGIN_CODE"
grep -o 'name="username"' /tmp/halo-login-resp.html >/dev/null && echo 'WARN: 仍在登录页（可能失败）'

echo '=== 4. 验证身份（me） ==='
curl -s -b /tmp/halo-login-cookie.txt "$SITE/apis/api.console.halo.run/v1alpha1/users/-" \
  | head -c 300; echo

echo '=== 5. 请求 bundle.js（3 次，看缓存头） ==='
for i in 1 2 3; do
  HDRS=$(curl -s -D - -o /dev/null -b /tmp/halo-login-cookie.txt "$SITE/apis/api.console.halo.run/v1alpha1/plugins/-/bundle.js")
  CACHE=$(printf '%s' "$HDRS" | grep -i 'X-Sam-Bundle-Cache' | tr -d '\r')
  HTTP=$(printf '%s' "$HDRS" | head -1 | tr -d '\r')
  LEN=$(printf '%s' "$HDRS" | grep -i 'content-length' | tr -d '\r')
  echo "req$i: $HTTP | $CACHE | $LEN"
done

echo '=== 6. bundle 是否含「小窝聊天」 ==='
curl -s -b /tmp/halo-login-cookie.txt "$SITE/apis/api.console.halo.run/v1alpha1/plugins/-/bundle.js" -o /tmp/bundle-check.js
grep -c '小窝聊天' /tmp/bundle-check.js || echo 'NOT FOUND'
grep -c 'SamHouseChat' /tmp/bundle-check.js || echo 'route NOT FOUND'

rm -f /tmp/halo-pw.txt /tmp/halo-pw.enc /tmp/halo-pub.pem /tmp/halo-login-cookie.txt
echo '=== done ==='
