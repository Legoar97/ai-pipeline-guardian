FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema si las necesitas
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copiar solo requirements primero (mejor cache de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código
COPY app/ app/

# Puerto por defecto de Cloud Run
EXPOSE 8080

# Comando para iniciar la aplicación
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]