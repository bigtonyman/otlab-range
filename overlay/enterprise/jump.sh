#!/bin/sh
# DMZ jump host: key-only sshd. It must not hold the workstation's private key.
rm -rf /home/analyst
exec /usr/sbin/sshd -D -e -f /opt/ent/sshd_config
