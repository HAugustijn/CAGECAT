FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV INSTALL_PATH=/cagecat_web

WORKDIR $INSTALL_PATH

COPY ./cagecat_web/ .

RUN apt-get update && apt-get install -y gcc libpq-dev build-essential curl && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip

RUN pip install ".[tools]"

EXPOSE 8004

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "cagecat_web.main:app", "--bind", "0.0.0.0:8004", "--workers", "2", "--timeout", "120"]
