FROM python:3.12-slim

WORKDIR /workspace

COPY app/requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt

CMD ["streamlit", "run", "app/dashboard/dashboard.py", "--server.address=0.0.0.0", "--server.port=8501"]
