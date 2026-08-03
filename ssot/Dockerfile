FROM python:3.12-slim

# sqlite3 CLI for init + interactive inspection; sqlite-web for the browser UI.
RUN apt-get update \
 && apt-get install -y --no-install-recommends sqlite3 \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir sqlite-web==0.6.4

WORKDIR /sql
COPY schema.sql seed.sql ./
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV DB_PATH=/data/ssot.db
VOLUME ["/data"]
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
