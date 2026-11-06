# Task 5: Subnetting 10.20.0.0/16

Rule: usable hosts = 2^(32 − prefix) − 2. Allocate from the largest requirement to the smallest,
starting at 10.20.0.0, each subnet directly after the previous one, with the smallest prefix that fits.

| Subnet | Hosts needed | Smallest block that fits | Network address | Prefix | Usable host range | Broadcast | Usable hosts |
|---|---|---|---|---|---|---|---|
| app | 1,000 | 2^10 − 2 = 1,022 ≥ 1,000 (2^9 − 2 = 510 is too small) | 10.20.0.0 | /22 | 10.20.0.1 – 10.20.3.254 | 10.20.3.255 | 1,022 |
| public | 250 | 2^8 − 2 = 254 ≥ 250 (2^7 − 2 = 126 is too small) | 10.20.4.0 | /24 | 10.20.4.1 – 10.20.4.254 | 10.20.4.255 | 254 |
| data | 100 | 2^7 − 2 = 126 ≥ 100 (2^6 − 2 = 62 is too small) | 10.20.5.0 | /25 | 10.20.5.1 – 10.20.5.126 | 10.20.5.127 | 126 |
| management | 20 | 2^5 − 2 = 30 ≥ 20 (2^4 − 2 = 14 is too small) | 10.20.5.128 | /27 | 10.20.5.129 – 10.20.5.158 | 10.20.5.159 | 30 |

## Working

1. **app** needs 1,000 hosts → 10 host bits → prefix 32 − 10 = /22, a block of 1,024 addresses
   (4 × 256). It starts at 10.20.0.0 and covers 10.20.0.0 – 10.20.3.255.
2. **public** starts right after, at 10.20.4.0. 250 hosts → 8 host bits → /24, 256 addresses:
   10.20.4.0 – 10.20.4.255.
3. **data** starts at 10.20.5.0. 100 hosts → 7 host bits → /25, 128 addresses: 10.20.5.0 – 10.20.5.127.
4. **management** starts at 10.20.5.128 (aligned, because 128 is a multiple of the /27 block size 32).
   20 hosts → 5 host bits → /27, 32 addresses: 10.20.5.128 – 10.20.5.159.

In each block the first address is the network address and the last is the broadcast address;
everything in between is usable. The four subnets use 10.20.0.0 – 10.20.5.159; the rest of the /16
(10.20.5.160 – 10.20.255.255) is free for later.

## NACL for the public subnet (`network/nacl.json`)

| Direction | Rule | Protocol / ports | Address | Action | Why |
|---|---|---|---|---|---|
| inbound | 90 | all | 198.51.100.0/24 | deny | abusive range, blocked even on 80/443 |
| inbound | 100 | TCP 80 | 0.0.0.0/0 | allow | HTTP to the load balancer |
| inbound | 110 | TCP 443 | 0.0.0.0/0 | allow | HTTPS to the load balancer |
| inbound | 120 | TCP 22 | 10.20.5.128/27 | allow | SSH only from management |
| inbound | 130 | TCP 1024–65535 | 10.20.0.0/22 | allow | replies from the app subnet (port 8000 → our ephemeral port) |
| outbound | 100 | TCP 8000 | 10.20.0.0/22 | allow | load balancer → app service |
| outbound | 110 | TCP 1024–65535 | 0.0.0.0/0 | allow | replies to clients' ephemeral ports |

Anything that matches no rule is denied by the implicit final rule. Checked with
`python tools/nacl_sim.py network/nacl.json network/packets_sample.jsonl --check` (6/6 correct,
output in `results/task5/nacl_check.txt`).

## Why stateless NACLs need reply rules, and why rule order matters

A NACL is **stateless**: it does not remember that a connection was opened, so every packet,
including the reply to a request we allowed, is checked against the rules on its own. A client's
request to port 443 is allowed inbound, but our response travels outbound to the client's
ephemeral port (1024–65535). Without an outbound rule for those ports the response is dropped.
Likewise, the replies from the app servers (source port 8000) arrive inbound on the load
balancer's ephemeral port and need their own inbound rule. A stateful security group would allow
these replies automatically.

Rules are evaluated **from the lowest number upward, and the first match decides**. A packet from
198.51.100.9 to port 443 matches both the deny for 198.51.100.0/24 and the allow for TCP 443 from
0.0.0.0/0. The deny therefore has number 90, lower than the allow rules (100, 110), so it is
reached first and the packet is dropped. If the deny were numbered above 110, the allow would
match first and the abusive range could still reach the web ports.
