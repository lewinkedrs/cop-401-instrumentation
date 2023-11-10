aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 209466391465.dkr.ecr.us-east-1.amazonaws.com
export tag_name=$(docker build -t riv-python:latest . | grep built | awk '{print $3}')
docker tag $tag_name 209466391465.dkr.ecr.us-east-1.amazonaws.com/riv-instrumentation:latest
docker push 209466391465.dkr.ecr.us-east-1.amazonaws.com/riv-instrumentation:latest
kubectl delete pod `kubectl get pods | grep flask | awk '{print $1}'`
