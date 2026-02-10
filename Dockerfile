FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080
ENV STREAMLIT_SERVER_PORT=$PORT

HEALTHCHECK CMD curl --fail http://localhost:$PORT || exit 1

ENTRYPOINT ["streamlit", "run", "app/app.py", "--server.port", "$PORT", "--server.address", "0.0.0.0"]
