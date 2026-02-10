FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

HEALTHCHECK CMD curl --fail http://localhost:$PORT || exit 1

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
