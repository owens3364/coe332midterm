FROM python:3.10-slim

COPY requirements.txt /coe332midterm/
WORKDIR /coe332midterm
RUN pip install -r requirements.txt
COPY __init__.py iss_tracker.py  /coe332midterm/
COPY test/__init__.py test/test_iss_tracker.py /coe332midterm/test/