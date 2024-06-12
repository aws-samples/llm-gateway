FROM public.ecr.aws/lambda/python:3.12@sha256:c54348db9f790f6206b8d2208ae6950f6957e0aa3df14aa6f2975f2d63a4a2a9

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt --no-cache-dir

ENV HOME /tmp

RUN chmod o+rx /root  # TODO: Can we delete this?

COPY app.py ${LAMBDA_TASK_ROOT}

WORKDIR /root

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1


CMD ["app.lambda_handler"]
