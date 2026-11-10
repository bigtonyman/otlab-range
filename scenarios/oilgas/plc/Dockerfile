ARG BASE=python:3.12-alpine
FROM ${BASE}
WORKDIR /app
RUN pip install --no-cache-dir "pymodbus==3.7.4"
COPY plc.py .
EXPOSE 502
CMD ["python3", "-u", "plc.py"]
