FROM python:3.10-slim

COPY requirements.txt /app/
WORKDIR /app
RUN pip install -r requirements.txt
COPY iss_tracker.py test/test_iss_tracker.py /app/