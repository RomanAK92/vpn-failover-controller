FROM python:3.12-alpine
WORKDIR /dashboard
COPY server.py index.html app.js profiles.js style.css ./
USER 65532:65532
CMD ["python3", "server.py", "--bind", "127.0.0.1"]
