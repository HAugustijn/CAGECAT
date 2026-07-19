FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV INSTALL_PATH=/cagecat_web

WORKDIR $INSTALL_PATH

# System packages: build tools + the aligners cblaster shells out to
# (hmmer for HMM search, diamond for local databases / makedb).
RUN apt-get update && apt-get install -y \
    gcc libpq-dev build-essential curl hmmer diamond-aligner \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

# Install third-party dependencies first so this heavy layer (cblaster, clinker,
# biopython, ...) stays cached across application source changes. Keep this list
# in sync with pyproject.toml [project].dependencies and the "tools" extra.
# Remote cblaster searches query NCBI over HTTP; for local searches also install
# NCBI BLAST+ / DIAMOND in this image.
RUN pip install \
    "fastapi>=0.115" "uvicorn[standard]>=0.30" "gunicorn>=21" "jinja2>=3.1" \
    "python-multipart>=0.0.9" "pydantic-settings~=2.0" "celery[redis]~=5.3" \
    "biopython~=1.83" cblaster clinker

# Startup hook that configures cblaster (NCBI e-mail) from the environment.
COPY ./compose/cagecat_web/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Copy the application and install the package itself (dependencies already met).
COPY ./cagecat_web/ .
RUN pip install --no-deps .

EXPOSE 8004

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "cagecat_web.main:app", "--bind", "0.0.0.0:8004", "--workers", "2", "--timeout", "120"]
