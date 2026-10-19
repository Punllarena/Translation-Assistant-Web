# Stages: base (python + spellcheck), edict (dictionary download), dev (adds node, the dev
# extras and Playwright's Chromium; source is bind-mounted), runtime (the default, last).

FROM python:3.12-slim AS base
# Spellcheck: enchant with the hunspell en_US dictionary (spec §5).
RUN apt-get update \
 && apt-get install -y --no-install-recommends libenchant-2-2 hunspell-en-us \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --chmod=755 docker/entrypoint.sh /usr/local/bin/ta-entrypoint
# A Windows checkout may have CRLF line endings, which break the shebang.
RUN sed -i 's/\r$//' /usr/local/bin/ta-entrypoint
ENTRYPOINT ["ta-entrypoint"]

# JParser / MeCab glosses: EDICT2 from the EDRDG (CC BY-SA 4.0), https://www.edrdg.org/
FROM base AS edict
ADD https://www.edrdg.org/pub/Nihongo/edict2.gz /tmp/edict2.gz
RUN mkdir -p /opt/ta && gunzip -c /tmp/edict2.gz > /opt/ta/edict2

FROM base AS dev
COPY --from=node:24-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:24-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
# Chromium (plus its system libraries) at the version web/package-lock.json pins.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
COPY web/package-lock.json /tmp/package-lock.json
RUN v=$(node -p 'require("/tmp/package-lock.json").packages["node_modules/@playwright/test"].version') \
 && npx --yes "playwright@$v" install --with-deps chromium \
 && rm -rf /root/.npm /tmp/package-lock.json
# Editable install: the image's copy of the source is replaced by the bind mount at /app.
COPY pyproject.toml alembic.ini ./
COPY api ./api
COPY tools ./tools
RUN pip install --no-cache-dir -e ".[dev,mecab]"
COPY --from=edict /opt/ta/edict2 /opt/ta/edict2
ENV TA_EDICT_PATH=/opt/ta/edict2 PYTHONPATH=/app TA_NPM_ENSURE=1
CMD ["serve-dev"]

FROM base AS runtime
# Source must be present before install: setuptools discovers api*/tools* at install time.
COPY pyproject.toml alembic.ini ./
COPY api ./api
COPY migrations ./migrations
COPY tools ./tools
RUN pip install --no-cache-dir ".[mecab]"
COPY --from=edict /opt/ta/edict2 /opt/ta/edict2
ENV TA_EDICT_PATH=/opt/ta/edict2
EXPOSE 8000
CMD ["serve"]
