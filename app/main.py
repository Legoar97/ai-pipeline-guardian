from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse
import json
import os
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Pipeline Guardian")

# Variables de entorno
GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET", "")

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <title>AI Pipeline Guardian</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                .status { color: #28a745; font-weight: bold; }
                .info { background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin-top: 20px; }
                code { background-color: #e9ecef; padding: 2px 5px; border-radius: 3px; }
            </style>
        </head>
        <body>
            <h1>🤖 AI Pipeline Guardian</h1>
            <p class="status">Status: Active ✅</p>
            <div class="info">
                <h3>Webhook Configuration:</h3>
                <p>URL: <code>POST /webhook</code></p>
                <p>GitLab Events: Pipeline Hook</p>
                <p>Secret Token: Configured via GITLAB_WEBHOOK_SECRET</p>
            </div>
        </body>
    </html>
    """

@app.post("/webhook")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: str = Header(None, alias="X-Gitlab-Token"),
    x_gitlab_event: str = Header(None, alias="X-Gitlab-Event")
):
    # Validar webhook secret
    if GITLAB_WEBHOOK_SECRET and x_gitlab_token != GITLAB_WEBHOOK_SECRET:
        logger.warning("Invalid webhook token")
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    
    # Obtener el body
    body = await request.json()
    
    logger.info(f"Received event: {x_gitlab_event}")
    logger.info(f"Project: {body.get('project', {}).get('name', 'Unknown')}")
    
    # Procesar eventos de pipeline
    if x_gitlab_event == "Pipeline Hook":
        object_attributes = body.get("object_attributes", {})
        status = object_attributes.get("status")
        
        if status == "failed":
            project_name = body.get("project", {}).get("name")
            pipeline_id = object_attributes.get("id")
            
            logger.info(f"Pipeline failed! Project: {project_name}, Pipeline ID: {pipeline_id}")
            # Aquí más tarde agregarás la lógica de IA
            
            return {
                "status": "received",
                "action": "will analyze failure",
                "pipeline_id": pipeline_id
            }
    
    return {"status": "received", "event": x_gitlab_event}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ai-pipeline-guardian"}