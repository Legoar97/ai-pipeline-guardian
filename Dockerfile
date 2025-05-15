# Usamos una imagen base de Python 3.11
FROM python:3.11-slim

# Establecemos el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copiamos el archivo de requisitos
COPY requirements.txt .

# Instalamos las dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos el código fuente del proyecto
COPY . .

# Exponemos el puerto en el que la aplicación estará corriendo
EXPOSE 8080

# Comando para ejecutar la aplicación con Uvicorn (apuntando a app.main)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
