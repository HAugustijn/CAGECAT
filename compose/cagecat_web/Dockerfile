FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV INSTALL_PATH=/cagecat_web

WORKDIR $INSTALL_PATH

# Fix here: copy content, not folder
COPY ./cagecat_web/ .

RUN apt-get update && apt-get install -y gcc libpq-dev build-essential curl && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
# Install the app together with the analysis tools (cblaster, clinker) so the
# Celery worker can execute them. Remote cblaster searches query NCBI over HTTP;
# for local searches also install NCBI BLAST+ / DIAMOND in this image.
RUN pip install ".[tools]"

EXPOSE 8004

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "cagecat_web.main:app", "--bind", "0.0.0.0:8004", "--workers", "2", "--timeout", "120"]
