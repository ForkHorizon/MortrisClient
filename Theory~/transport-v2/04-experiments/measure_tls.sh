#!/bin/sh
# Measures FULL TLS handshake bytes (as counted by openssl s_client: TLS records, excluding TCP/IP headers).
# Evidence for "a cold connection costs more than a typical batch body". Hosts are public endpoints of well-known
# services, used only as examples of real certificate chains; the real analytics host will differ.
# Resumed-handshake sizes are NOT measured here: s_client's counters proved unreliable for resumption in our runs,
# so 01/03 docs use RFC 8446 reasoning for resumption instead.
# Run: sh measure_tls.sh > results/tls.txt
openssl version
for h in www.cloudflare.com www.google.com api2.amplitude.com app-measurement.com; do
  for groups in X25519MLKEM768:X25519 X25519; do
    r=$( (sleep 2; echo) | openssl s_client -connect $h:443 -servername $h -tls1_3 -groups $groups 2>/dev/null \
      | grep -E "handshake has read|Negotiated TLS1.3 group" | tr '\n' ' ')
    echo "$h tls1.3 groups=$groups :: $r"
  done
  r=$(echo | openssl s_client -connect $h:443 -servername $h -tls1_2 2>/dev/null | grep "handshake has read")
  echo "$h tls1.2 :: $r"
done
