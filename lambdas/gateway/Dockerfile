FROM python:3.12-slim

WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /app/requirements.txt

COPY ./api /app/api

ARG LLM_GATEWAY_VCPUS
ENV LLM_GATEWAY_VCPUS=$LLM_GATEWAY_VCPUS

CMD uvicorn api.app:app --host 0.0.0.0 --port 80 --workers $LLM_GATEWAY_VCPUS