# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DRUGAGENT_HOST=0.0.0.0 \
    DRUGAGENT_PORT=8077 \
    DRUGAGENT_REPORTS_DIR=/app/storage/reports \
    DRUGAGENT_CACHE_DIR=/app/storage/cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libxrender1 libxext6 libgomp1 libexpat1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock ./
# Optional CA is for managed build environments; it is never stored in an image layer.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    python -m pip install --no-cache-dir --require-hashes -r requirements.lock

RUN groupadd --gid 10001 drugagent \
    && useradd --uid 10001 --gid drugagent --create-home drugagent \
    && mkdir -p /app/storage/reports /app/storage/cache \
    && chown -R drugagent:drugagent /app/storage

COPY --chown=drugagent:drugagent agents.py config.py llm.py web.py run.py check_env.py LICENSE ./
COPY --chown=drugagent:drugagent drugagent/ ./drugagent/
COPY --chown=drugagent:drugagent tools/ ./tools/
COPY --chown=drugagent:drugagent web/ ./web/
COPY --chown=drugagent:drugagent data/ ./data/

USER drugagent
RUN python -c "from drugagent.api import create_app; from rdkit import Chem; from rdkit.Chem import Draw; assert create_app().title == 'DrugAgent'; assert Draw.MolToImage(Chem.MolFromSmiles('CCO')).size == (300, 300)"
EXPOSE 8077
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-m", "drugagent.healthcheck"]
CMD ["python", "web.py"]
