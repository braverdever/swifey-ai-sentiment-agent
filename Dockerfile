FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
build-essential \
git \
&& rm -rf /var/lib/apt/lists/*

WORKDIR /

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]