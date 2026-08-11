FROM python:3.14-alpine

RUN pip install --no-cache-dir watchdog

WORKDIR /app

COPY date_restore.py /app/date_restore.py

RUN chmod 755 -R /app

ENTRYPOINT ["python3", "-u", "/app/date_restore.py"]
