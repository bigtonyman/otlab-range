#!/usr/bin/env python3
"""Upload a PCAP to the local MarlinSpike, start a scan, wait, print a summary.

Runs ON the MarlinSpike host. Reads the admin password from the
MarlinSpike .env itself and never prints it.

usage: ms_submit.py <pcap> [project_id]
"""
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:5001"
ENV = os.path.expanduser("~/Projects/marlinspike/.env")

with open(ENV) as fh:
    PW = next(ln.split("=", 1)[1].strip() for ln in fh if ln.startswith("ADMIN_PASSWORD="))

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(path, data=None, headers=None):
    req = urllib.request.Request(BASE + path, data=data, headers=headers or {})
    with opener.open(req, timeout=300) as resp:
        return resp.read().decode()


def csrf_token():
    return re.search(r'name="csrf-token" content="([^"]+)"', call("/scans")).group(1)


def main():
    pcap = sys.argv[1]
    pid = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    name = os.path.basename(pcap)

    call("/login", urllib.parse.urlencode({"username": "admin", "password": PW}).encode())
    tok = csrf_token()  # rotated at login

    boundary = uuid.uuid4().hex
    with open(pcap, "rb") as fh:
        payload = fh.read()
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + payload + f"\r\n--{boundary}--\r\n".encode()
    up = json.loads(call(
        f"/api/projects/{pid}/upload", body,
        {"Content-Type": f"multipart/form-data; boundary={boundary}", "X-CSRF-Token": tok},
    ))
    print("upload:", json.dumps(up)[:400])
    if not up.get("ok"):
        sys.exit(1)

    fname = up.get("filename") or up.get("file") or name
    start = json.loads(call(
        "/api/scans/start",
        json.dumps({"pcap_file": fname, "project_id": pid}).encode(),
        {"Content-Type": "application/json", "X-CSRF-Token": tok},
    ))
    print("start:", json.dumps(start)[:400])
    if not start.get("ok", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
