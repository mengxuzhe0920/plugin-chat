#!/bin/bash
# 登录后抓 Console/UC 首页 HTML，列出所有 js/css 资产及大小
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

echo '=== /console/ 资产 ==='
curl -s -b /tmp/ck.txt "$SITE/console/" -o /tmp/console.html
echo "html size: $(stat -c%s /tmp/console.html)"
grep -oE '(src|href)="[^"]+\.(js|css)[^"]*"' /tmp/console.html | sed 's/^[a-z]*="//;s/"$//' | sort -u | head -30

echo '=== /uc/ 资产（同一 SPA，一般一样） ==='
curl -s -b /tmp/ck.txt "$SITE/uc/" -o /tmp/uc.html
echo "html size: $(stat -c%s /tmp/uc.html)"

echo '=== 每个资产的实测大小/耗时 ==='
for U in $(grep -oE '(src|href)="[^"]+\.(js|css)[^"]*"' /tmp/console.html | sed 's/^[a-z]*="//;s/"$//' | sort -u | head -30); do
  case "$U" in
    http*) FULL="$U" ;;
    /*) FULL="$SITE$U" ;;
    *) FULL="$SITE/$U" ;;
  esac
  curl -s -b /tmp/ck.txt -o /dev/null -w "  %{http_code} t=%{time_total}s size=%{size_download}  $U\n" "$FULL"
done

rm -f /tmp/pw.txt /tmp/pw.enc /tmp/p.pem /tmp/ck.txt /tmp/l.html /tmp/console.html /tmp/uc.html
echo done
