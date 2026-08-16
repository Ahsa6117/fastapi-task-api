# The build recipe for this app's own image, in two stages.
#
# Stage 1 (builder) installs the dependencies into a virtualenv. Stage 2
# starts from a clean base and copies only that finished virtualenv over.
# Nothing used to *build* the image -- pip, its cache, setuptools, wheel,
# any compiler a package pulled in -- exists in what ships.
#
# Docker only keeps the final stage. The builder is scratch work.

# ---------- stage 1: build the dependencies ----------
FROM python:3.12-slim AS builder

# A venv is the cleanest thing to hand to the next stage: one directory
# containing exactly the packages, and nothing about how they got there.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements.txt on its own first. Docker caches each step and
# re-runs one only when its inputs change, so editing main.py does not
# re-download every dependency. Copying the code first would throw that
# cache away on every single edit.
# requirements-runtime.txt, not requirements.txt: the server needs fastapi
# and uvicorn, not the fastapi CLI, rich, typer, httpx and jinja2 that come
# with fastapi[standard]. Those are for developing, not for serving.
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

# pip did its job in this stage and is not needed in the next one -- the
# running app never installs anything. Dropping it (and setuptools and
# wheel) is the difference between a venv and a shipped venv.
RUN pip uninstall -y pip setuptools wheel 2>/dev/null || true; \
    rm -rf /opt/venv/lib/python3.12/site-packages/pip* \
           /opt/venv/lib/python3.12/site-packages/setuptools* \
           /opt/venv/lib/python3.12/site-packages/wheel* \
           /opt/venv/lib/python3.12/site-packages/pkg_resources \
           /opt/venv/bin/pip*


# ---------- stage 2: the image that actually ships ----------
FROM python:3.12-slim

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Name the files instead of "COPY . ." -- an allowlist rather than a
# denylist. .dockerignore still excludes .env, but this way the image
# cannot leak a file nobody remembered to exclude. (Borrowed from the
# AI's version in the Stage 6 review, which did this better than I did.)
COPY main.py db.py ./

EXPOSE 3000

# 0.0.0.0, not 127.0.0.1: inside a container, 127.0.0.1 means "only this
# container", so the port mapping would reach nothing.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3000"]
