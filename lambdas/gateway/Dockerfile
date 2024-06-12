FROM public.ecr.aws/lambda/python:3.12@sha256:c54348db9f790f6206b8d2208ae6950f6957e0aa3df14aa6f2975f2d63a4a2a9

RUN useradd -d /home/username -m -s /bin/bash llm-user
USER llm-user

COPY ./api ./api

COPY requirements.txt .

RUN pip3 install -r requirements.txt -U --no-cache-dir

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

CMD [ "api.app.handler" ]