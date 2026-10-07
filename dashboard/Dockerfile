FROM python:3.12-alpine
WORKDIR /dashboard
COPY server.py history.py accounts.py drafts.py control.py support.py mirror.py login.js drafts.js management.js index.html app.js profiles.js style.css ./
RUN mkdir /history /auth && chown 65532:65532 /history /auth && chmod 700 /history /auth
USER 65532:65532
CMD ["python3", "server.py", "--bind", "127.0.0.1", "--history", "/history"]
