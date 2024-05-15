FROM public.ecr.aws/lambda/python:3.11

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

ENV HOME /tmp

RUN chmod o+rx /root  # TODO: Can we delete this?

COPY app.py ${LAMBDA_TASK_ROOT}

WORKDIR /root

CMD ["app.lambda_handler"]
