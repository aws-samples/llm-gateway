FROM public.ecr.aws/lambda/python:3.12@sha256:c54348db9f790f6206b8d2208ae6950f6957e0aa3df14aa6f2975f2d63a4a2a9

COPY ./api ./api

COPY requirements.txt .

RUN pip3 install -r requirements.txt -U --no-cache-dir

CMD [ "api.app.handler" ]