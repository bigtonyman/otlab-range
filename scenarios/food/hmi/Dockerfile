# FUXA with its Modbus driver baked in. The upstream image ships without the optional `modbus-serial` plugin,
# so a ModbusTCP device logs "plugin is missing!" and never polls OpenPLC. FUXA's own plugin registry pins 8.0.19.
# Same fix as scenarios/oilgas/hmi/Dockerfile; food's FUXA uses the same stock digest.
ARG FUXA_IMAGE
FROM ${FUXA_IMAGE}
WORKDIR /usr/src/app/FUXA/server
RUN npm install --no-save --no-audit --no-fund modbus-serial@8.0.19 && node -e "require('modbus-serial')"
