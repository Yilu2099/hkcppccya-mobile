FROM python:3.12-slim
WORKDIR /app
COPY admin/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
ENV ZQ_CMS_BIND=0.0.0.0
CMD ["python3", "admin/server.py"]
