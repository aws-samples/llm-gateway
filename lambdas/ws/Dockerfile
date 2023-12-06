# Copyright 2023 Amazon.com, Inc. and its affiliates. All Rights Reserved.
#
# Licensed under the Amazon Software License (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#   http://aws.amazon.com/asl/
#
# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

FROM public.ecr.aws/lambda/python:3.9

COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

ENV HOME /tmp

RUN chmod o+rx /root
RUN mkdir -p /root/.aws/models/bedrock-runtime
COPY bedrock-runtime /root/.aws/models/bedrock-runtime/

COPY app.py ${LAMBDA_TASK_ROOT}

WORKDIR /root

CMD ["app.lambda_handler"]
