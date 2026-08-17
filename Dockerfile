FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p data/logs data/resources

EXPOSE 7860

CMD ["python", "树剪.py", "--web"]
