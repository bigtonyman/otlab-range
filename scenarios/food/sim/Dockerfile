ARG BASE
FROM ${BASE}
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
WORKDIR /usr/src/app
COPY simulators/ /usr/src/app/
ENTRYPOINT ["python", "main.py", "run", "-c"]
