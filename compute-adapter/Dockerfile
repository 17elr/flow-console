FROM python:3.12-slim
WORKDIR /compute
COPY compute-adapter/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY compute-adapter/app.py .
RUN useradd -u 10002 compute && mkdir /compute/cache && chown -R compute:compute /compute
USER compute
CMD ["uvicorn","app:app","--host","0.0.0.0","--port","8100","--limit-concurrency","4"]
