pip install botocore==1.31.58
cp -r "$(pip show botocore | grep Location | cut -d " " -f 2)/botocore/data/bedrock-runtime" ./bedrock-runtime
