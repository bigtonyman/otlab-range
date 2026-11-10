ARG BASE
FROM ${BASE}
ARG OPENPLC_REPO
ARG OPENPLC_COMMIT
# The base image ships its snapshot.debian.org lines commented out; use them (frozen at 2021-12-01, reproducible).
RUN grep '^# deb http://snapshot' /etc/apt/sources.list | sed 's/^# //' > /tmp/s.list && mv /tmp/s.list /etc/apt/sources.list \
    && echo 'Acquire::Check-Valid-Until "false";' > /etc/apt/apt.conf.d/99archive \
    && apt-get update && apt-get -y install --no-install-recommends git ca-certificates sqlite3 sudo \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN git clone --no-checkout "$OPENPLC_REPO" /OpenPLC_v3 \
    && git -C /OpenPLC_v3 checkout -q "$OPENPLC_COMMIT" \
    && [ "$(git -C /OpenPLC_v3 rev-parse HEAD)" = "$OPENPLC_COMMIT" ]
WORKDIR /OpenPLC_v3
RUN ./install.sh docker
COPY entrypoint.sh /OpenPLC_v3/entrypoint.sh
EXPOSE 502 8080
