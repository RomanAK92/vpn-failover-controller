FROM python:3.12-alpine
WORKDIR /dashboard
COPY server.py history.py index.html app.js profiles.js style.css ./
RUN mkdir /history && chown 65532:65532 /history && chmod 700 /history
USER 65532:65532
CMD ["python3", "server.py", "--bind", "127.0.0.1", "--history", "/history"]
