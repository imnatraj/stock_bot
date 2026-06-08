FROM python:3.12-slim

WORKDIR /app

# copy only source to keep build context small
COPY ./src ./src
COPY README.md ./README.md
COPY requirements.txt ./requirements.txt

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

RUN python -m pip install --upgrade pip
RUN python -m pip install --no-cache-dir -r requirements.txt

CMD ["python", "-m", "stock_bot"]
