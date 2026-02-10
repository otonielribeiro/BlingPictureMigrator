FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Streamlit agora lê a porta de .streamlit/config.toml
# Não é necessário EXPOSE ou ENV STREAMLIT_SERVER_PORT aqui, pois o healthcheck e o config.toml já cuidam.

HEALTHCHECK CMD curl --fail http://localhost:$PORT || exit 1

ENTRYPOINT ["streamlit", "run", "app/app.py"]
