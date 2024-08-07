FROM public.ecr.aws/docker/library/alpine:edge@sha256:e31c3b1cd47718260e1b6163af0a05b3c428dc01fa410baf72ca8b8076e22e72
RUN apk update && apk add python3 py3-pip py3-pyarrow curl --no-cache
RUN addgroup -S streamlit && adduser -S -G streamlit streamlit

# Create the directory for Streamlit configuration
RUN mkdir -p /home/streamlit/.streamlit && chown -R streamlit:streamlit /home/streamlit/.streamlit

RUN mkdir /app && chown streamlit:streamlit /app
RUN mkdir /app/data && chown streamlit:streamlit /app/data
RUN mkdir /app/pages2 && chown streamlit:streamlit /app/pages2

COPY requirements.txt /app/
WORKDIR /app
RUN pip3 install --break-system-packages -r requirements.txt --no-cache-dir
COPY app.py /app/
COPY common.py /app/
COPY invoke_llm_with_streaming.py /app/
COPY data/cost_db.csv /app/data/
COPY pages2/apikey_create.py /app/pages2/
COPY pages2/apikey_get.py /app/pages2/
COPY pages2/quota_status.py /app/pages2/
COPY pages2/manage_model_access.py /app/pages2/
COPY pages2/manage_quotas.py /app/pages2/

# Copy the Streamlit configuration file
COPY config.toml /home/streamlit/.streamlit/

USER streamlit
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8501/healthz || exit 1
CMD ["/usr/bin/streamlit", "run", "app.py"]
