from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse
import json
import os
import logging
import aiohttp
from app.gitlab_client import GitLabClient
from app.ai_analyzer import AIAnalyzer

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Pipeline Guardian")

# Variables de entorno
GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET", "")

# Inicializar clientes
gitlab_client = GitLabClient()
ai_analyzer = AIAnalyzer()

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
        <head>
            <title>AI Pipeline Guardian</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; background-color: #f5f5f5; }
                .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .status { color: #28a745; font-weight: bold; font-size: 1.2em; }
                .info { background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-top: 20px; }
                code { background-color: #e9ecef; padding: 3px 6px; border-radius: 3px; font-family: monospace; }
                .feature { margin: 15px 0; padding-left: 25px; position: relative; }
                .feature:before { content: "✓"; position: absolute; left: 0; color: #28a745; font-weight: bold; }
                h1 { color: #333; }
                h3 { color: #555; margin-top: 25px; }
                .badge { display: inline-block; padding: 5px 10px; border-radius: 15px; font-size: 0.85em; margin-left: 10px; }
                .badge-ai { background-color: #7c3aed; color: white; }
                .badge-ready { background-color: #28a745; color: white; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 AI Pipeline Guardian <span class="badge badge-ai">AI-Powered</span></h1>
                <p class="status">Status: Active <span class="badge badge-ready">Ready</span></p>
                
                <div class="info">
                    <h3>Configuration</h3>
                    <p><strong>Webhook URL:</strong> <code>POST /webhook</code></p>
                    <p><strong>GitLab Events:</strong> Pipeline Hook</p>
                    <p><strong>AI Model:</strong> Vertex AI (Gemini Pro) 🧠</p>
                    <p><strong>Project:</strong> <code>ai-pipeline-guardian</code></p>
                    
                    <h3>Features</h3>
                    <div class="feature">Automatic failure analysis with AI</div>
                    <div class="feature">Smart retry for transient errors</div>
                    <div class="feature">Intelligent comments on MRs and commits</div>
                    <div class="feature">Root cause identification</div>
                    <div class="feature">Actionable solution suggestions</div>
                    
                    <h3>Error Categories</h3>
                    <div class="feature">Network/timeout issues → Auto-retry</div>
                    <div class="feature">Test failures → Detailed analysis</div>
                    <div class="feature">Dependency errors → Fix suggestions</div>
                    <div class="feature">Syntax errors → Code corrections</div>
                    <div class="feature">Configuration issues → Setup guidance</div>
                </div>
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
            project = body.get("project", {})
            project_id = project.get("id")
            project_name = project.get("name")
            pipeline_id = object_attributes.get("id")
            ref = object_attributes.get("ref", "unknown")
            
            logger.info(f"Pipeline failed! Project: {project_name}, Pipeline ID: {pipeline_id}, Branch: {ref}")
            
            # Analizar el fallo con IA
            try:
                # Obtener jobs del pipeline
                jobs = await gitlab_client.get_pipeline_jobs(project_id, pipeline_id)
                
                # Buscar jobs fallidos
                failed_jobs = [job for job in jobs if job.get("status") == "failed"]
                logger.info(f"Found {len(failed_jobs)} failed jobs")
                
                analyzed_count = 0
                retry_count = 0
                comment_count = 0
                
                for job in failed_jobs:
                    job_id = job.get("id")
                    job_name = job.get("name")
                    
                    logger.info(f"Analyzing failed job: {job_name} (ID: {job_id})")
                    
                    # Obtener log del job
                    job_log = await gitlab_client.get_job_trace(project_id, job_id)
                    if not job_log:
                        logger.warning(f"No log found for job {job_name}")
                        continue
                    
                    # Analizar con IA
                    logger.info(f"Sending log to AI for analysis...")
                    analysis = await ai_analyzer.analyze_failure(job_log, job_name)
                    analyzed_count += 1
                    
                    logger.info(f"AI Analysis: Category={analysis['error_category']}, Action={analysis['recommended_action']}")
                    
                    # Tomar acción basada en el análisis
                    if analysis["recommended_action"] == "reintentar" and analysis["error_category"] == "transitorio":
                        logger.info(f"AI recommends retry for transient error in job {job_name}")
                        success = await gitlab_client.retry_job(project_id, job_id)
                        if success:
                            retry_count += 1
                            logger.info(f"Successfully retried job {job_name}")
                        else:
                            logger.error(f"Failed to retry job {job_name}")

                    # Crear comentario con el análisis
                    comment = f"""🤖 **AI Pipeline Guardian Analysis**

**Pipeline:** #{pipeline_id} on `{ref}`
**Job:** `{job_name}`
**Status:** Failed ❌

**🔍 Error Analysis:**
{analysis['error_explanation']}

**📁 Category:** `{analysis['error_category']}`
**🎯 Recommended Action:** `{analysis['recommended_action']}`

**💡 Suggested Solution:**
{analysis['suggested_solution']}

---
*This analysis was generated automatically by AI Pipeline Guardian*"""
                    
                    # Inicializar comentario posteado
                    comment_posted = False
                    
                    # Por ahora, loguear el comentario
                    logger.info(f"Analysis comment:\n{comment}")
                    
                    # Intentar comentar en el commit más reciente del proyecto
                    try:
                        # Para commits directo en main
                        commits = body.get("commits", [])
                        if commits:
                            # Usar el último commit
                            commit_sha = commits[-1].get("id")
                            if commit_sha:
                                success = await gitlab_client.create_commit_comment(
                                    project_id, commit_sha, comment
                                )
                                if success:
                                    comment_posted = True
                                    comment_count += 1
                                    logger.info(f"Posted comment to commit {commit_sha[:8]}")
                                else:
                                    logger.error("Failed to post comment to commit")
                    except Exception as e:
                        logger.error(f"Error posting commit comment: {e}")
                    
                    # Si no se pudo comentar en commit, intentar en MR
                    if not comment_posted:
                        try:
                            merge_request = body.get("merge_request")
                            if merge_request:
                                mr_iid = merge_request.get("iid")
                                if mr_iid:
                                    # Verificar si el método está implementado
                                    if hasattr(gitlab_client, 'create_merge_request_note'):
                                        success = await gitlab_client.create_merge_request_note(
                                            project_id, mr_iid, comment
                                        )
                                        if success:
                                            comment_posted = True
                                            comment_count += 1
                                            logger.info(f"Posted comment to MR #{mr_iid}")
                                    else:
                                        logger.warning("create_merge_request_note method not implemented")
                        except Exception as e:
                            logger.error(f"Error posting MR comment: {e}")
                    
                    # Si todo falla, al menos logueamos el análisis
                    if not comment_posted:
                        logger.warning("Could not post comment to GitLab, but analysis was completed")
                
                summary = {
                    "status": "analyzed",
                    "action": "AI analysis complete",
                    "pipeline_id": pipeline_id,
                    "jobs_analyzed": analyzed_count,
                    "jobs_retried": retry_count,
                    "comments_posted": comment_count
                }
                
                logger.info(f"Analysis complete: {summary}")
                return summary
                
            except Exception as e:
                logger.error(f"Error processing pipeline failure: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return {
                    "status": "error",
                    "message": str(e)
                }
    
    return {"status": "received", "event": x_gitlab_event}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ai-pipeline-guardian",
        "ai": "vertex-ai-gemini-pro",
        "version": "1.0.0"
    }

@app.get("/stats")
async def get_stats():
    """Endpoint para estadísticas (futuro)"""
    return {
        "total_pipelines_analyzed": 0,
        "success_rate": 0,
        "ai_model": "gemini-pro"
    }

@app.get("/debug-token")
async def debug_token():
    """Endpoint para depurar el token de GitLab (solo desarrollo)"""
    token = os.getenv("GITLAB_ACCESS_TOKEN", "")
    return {
        "token_present": bool(token),
        "token_length": len(token) if token else 0,
        "token_prefix": token[:4] + "..." if token else ""
    }