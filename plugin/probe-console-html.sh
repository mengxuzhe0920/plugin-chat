#!/bin/bash
# 看 console/uc HTML 是否含用户特定内容（CSRF、用户名等）
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

curl -s -b /tmp/ck.txt "$SITE/console/" -o /tmp/c1.html
sleep 2
curl -s -b /tmp/ck.txt "$SITE/console/" -o /tmp/c2.html
echo "=== console HTML 两次是否一致 ==="
if diff -q /tmp/c1.html /tmp/c2.html >/dev/null; then echo "IDENTICAL"; else echo "DIFFERENT"; diff /tmp/c1.html /tmp/c2.html | head -10; fi
echo "=== 是否含 csrf/token/用户名 ==="
grep -oiE "csrf|xsrf|token|workbuddy|session" /tmp/c1.html | sort | uniq -c
echo "=== console HTML 大小与内容预览 ==="
wc -c /tmp/c1.html
head -c 600 /tmp/c1.html; echo
echo "=== uc HTML 同样检查 ==="
curl -s -b /tmp/ck.txt "$SITE/uc/" -o /tmp/u1.html
sleep 2
curl -s -b /tmp/ck.txt "$SITE/uc/" -o /tmp/u2.html
diff -q /tmp/u1.html /tmp/u2.html >/dev/null && echo "UC IDENTICAL" || { echo "UC DIFFERENT"; diff /tmp/u1.html /tmp/u2.html | head -10; }
grep -oiE "csrf|xsrf|token|workbuddy|session" /tmp/u1.html | sort | uniq -c
wc -c /tmp/u1.html

rm -f /tmp/pw.txt /tmp/pw.enc /tmp/p.pem /tmp/ck.txt /tmp/l.html /tmp/c1.html /tmp/c2.html /tmp/u1.html /tmp/u2.html
echo done
