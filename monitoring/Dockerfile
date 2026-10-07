FROM python:3.12-alpine
WORKDIR /reporter
COPY kuma_push.py ./
USER 65532:65532
ENTRYPOINT ["python3", "-B", "kuma_push.py"]
