FROM docker:28.5.2-dind-rootless@sha256:7c3e797187e43738220462658f4586572cbd3bf009f728b21e34d9c5c06ce431

USER root
RUN apk add --no-cache bash curl git python3 py3-pip \
    && mkdir -p /opt/uv-bin \
    && curl -LsSf https://astral.sh/uv/install.sh \
       | env UV_UNMANAGED_INSTALL=/opt/uv-bin sh \
    && python3 -m venv /opt/runner-venv \
    && /opt/runner-venv/bin/pip install --no-cache-dir \
       claude-agent-sdk dirhash fastapi httpx jinja2 litellm==1.83.14 packaging \
       pathspec psutil pydantic python-dotenv pyyaml requests rich ruff \
       shortuuid supabase tenacity toml typer uvicorn \
    && /opt/runner-venv/bin/pip install --no-cache-dir --no-deps \
       harbor==0.9.0 \
    && /opt/runner-venv/bin/harbor --help >/dev/null

COPY --chown=rootless:rootless dataset /opt/dataset
COPY --chown=rootless:rootless coding_kid.whl /opt/coding_kid-0.1.0-py3-none-any.whl
COPY --chown=rootless:rootless coding_kid_harbor.py /opt/coding_kid_harbor.py
COPY --chown=rootless:rootless host-network.yaml /opt/host-network.yaml
COPY --chown=rootless:rootless runner.py /opt/runner.py
COPY --chown=rootless:rootless entrypoint.sh /opt/entrypoint.sh

RUN chmod +x /opt/entrypoint.sh && mkdir -p /workspace/jobs

ENV PATH="/opt/runner-venv/bin:${PATH}" \
    PYTHONPATH=/opt \
    PYTHONUNBUFFERED=1 \
    CODING_KID_BENCH_WHEEL=/opt/coding_kid-0.1.0-py3-none-any.whl \
    CODING_KID_BENCH_UV=/opt/uv-bin/uv \
    PIP_INDEX_URL=https://pypi.org/simple/

EXPOSE 8080
ENTRYPOINT ["/opt/entrypoint.sh"]
