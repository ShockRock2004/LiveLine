FROM python:3.12-slim
WORKDIR /app

RUN pip install --no-cache-dir nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*"
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tools/download_models.py tools/
RUN python tools/download_models.py \
 && python -c "from faster_whisper import download_model; download_model('base.en')"

COPY liveline liveline
ENV LIVELINE_SETTINGS_FILE=/app/state/settings.json
EXPOSE 8000
CMD ["python", "-m", "liveline"]
