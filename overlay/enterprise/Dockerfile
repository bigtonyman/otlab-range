# One image for every enterprise-overlay role (firewall, IT workstation, intranet, jump host, historian mirror).
# Build context is overlay/ (needs mb.py). Lab shortcut: the workstation key pair and the jump host's host keys
# are generated here, so they are stable per build and identical across roles; entrypoints remove what a role
# must not hold.
ARG BASE=python:3.12-alpine
FROM ${BASE}
RUN apk add --no-cache nftables openssh curl nmap iproute2 tcpdump \
 && pip install --no-cache-dir "pymodbus==3.7.4" "asyncua==1.1.5" \
 && ssh-keygen -A \
 && adduser -D -s /bin/sh analyst && adduser -D -s /bin/sh jump \
 && sed -i 's/^jump:!/jump:*/' /etc/shadow \
 && mkdir -p -m 700 /home/analyst/.ssh /home/jump/.ssh \
 && ssh-keygen -q -t ed25519 -N '' -C analyst@it-ws -f /home/analyst/.ssh/id_ed25519 \
 && cp /home/analyst/.ssh/id_ed25519.pub /home/jump/.ssh/authorized_keys \
 && echo "10.213.20.10 $(cat /etc/ssh/ssh_host_ed25519_key.pub)" > /home/analyst/.ssh/known_hosts \
 && printf 'Host jump\n  HostName 10.213.20.10\n  User jump\n  LogLevel ERROR\n' > /home/analyst/.ssh/config \
 && chmod 600 /home/jump/.ssh/authorized_keys /home/analyst/.ssh/config \
 && chown -R analyst:analyst /home/analyst/.ssh && chown -R jump:jump /home/jump/.ssh
COPY mb.py /usr/local/bin/mb.py
RUN printf '#!/bin/sh\nexec python3 /usr/local/bin/mb.py "$@"\n' > /usr/local/bin/mb && chmod 755 /usr/local/bin/mb
COPY enterprise/fw.sh enterprise/jump.sh enterprise/hist.py enterprise/sshd_config /opt/ent/
COPY enterprise/www /opt/ent/www
RUN chmod 755 /opt/ent/fw.sh /opt/ent/jump.sh
