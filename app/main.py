from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse
import json
import os
import logging
import aiohttp
from app.gitlab_client import GitLabClient
from app.ai_analyzer import AIAnalyzer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Pipeline Guardian")

# Environment variables
GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET", "")

# Initialize clients
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
                    <p><strong>AI Model:</strong> Vertex AI (Gemini 2.0 Flash) 🧠</p>
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
    # Validate webhook secret
    if GITLAB_WEBHOOK_SECRET and x_gitlab_token != GITLAB_WEBHOOK_SECRET:
        logger.warning("Invalid webhook token")
        raise HTTPException(status_code=401, detail="Invalid webhook token")
    
    # Get the body
    body = await request.json()
    
    logger.info(f"Received event: {x_gitlab_event}")
    logger.info(f"Project: {body.get('project', {}).get('name', 'Unknown')}")
    
    # Process pipeline events
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
            
            # Analyze the failure with AI
            try:
                # Get jobs from the pipeline
                jobs = await gitlab_client.get_pipeline_jobs(project_id, pipeline_id)
                
                # Find failed jobs
                failed_jobs = [job for job in jobs if job.get("status") == "failed"]
                logger.info(f"Found {len(failed_jobs)} failed jobs")
                
                analyzed_count = 0
                retry_count = 0
                comment_count = 0
                
                for job in failed_jobs:
                    job_id = job.get("id")
                    job_name = job.get("name")
                    
                    logger.info(f"Analyzing failed job: {job_name} (ID: {job_id})")
                    
                    # Get job log
                    job_log = await gitlab_client.get_job_trace(project_id, job_id)
                    if not job_log:
                        logger.warning(f"No log found for job {job_name}")
                        continue
                    
                    # Analyze with AI
                    logger.info(f"Sending log to AI for analysis...")
                    analysis = await ai_analyzer.analyze_failure(job_log, job_name)
                    analyzed_count += 1
                    
                    logger.info(f"AI Analysis: Category={analysis['error_category']}, Action={analysis['recommended_action']}")
                    
                    # Take action based on analysis
                    if analysis["recommended_action"] == "retry" and analysis["error_category"] == "transient":
                        logger.info(f"AI recommends retry for transient error in job {job_name}")
                        success = await gitlab_client.retry_job(project_id, job_id)
                        if success:
                            retry_count += 1
                            logger.info(f"Successfully retried job {job_name}")
                        else:
                            logger.error(f"Failed to retry job {job_name}")

                    # Create a comment with the analysis
                    # Using Unicode emojis for compatibility with GitLab
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
                    
                    # Initialize comment posted
                    comment_posted = False
                    
                    # Log the comment
                    logger.info(f"Analysis comment:\n{comment}")
                    
                    # Try to comment on the most recent commit of the project
                    try:
                        # First look in the webhook commits
                        commits = body.get("commits", [])
                        commit_sha = None
                        
                        if commits and len(commits) > 0:
                            # Use the last commit
                            commit_sha = commits[-1].get("id")
                            logger.info(f"Found commit in webhook payload: {commit_sha[:8] if commit_sha else 'None'}")
                        
                        # If no commits in webhook, get from pipeline details
                        if not commit_sha:
                            # Get pipeline details
                            pipeline_details = await gitlab_client.get_pipeline_details(project_id, pipeline_id)
                            commit_sha = pipeline_details.get("sha")
                            logger.info(f"Found commit from pipeline details: {commit_sha[:8] if commit_sha else 'None'}")
                        
                        # If we still don't have the commit, get the latest from the branch
                        if not commit_sha:
                            # Get latest commit from the branch
                            commit_info = await gitlab_client.get_latest_commit(project_id, ref)
                            commit_sha = commit_info.get("id")
                            logger.info(f"Found latest commit from branch: {commit_sha[:8] if commit_sha else 'None'}")
                        
                        if commit_sha:
                            logger.info(f"Posting comment to commit {commit_sha[:8]}")
                            success = await gitlab_client.create_commit_comment(
                                project_id, commit_sha, comment
                            )
                            if success:
                                comment_posted = True
                                comment_count += 1
                                logger.info(f"Posted comment to commit {commit_sha[:8]}")
                            else:
                                logger.error("Failed to post comment to commit")
                        else:
                            logger.warning("No commit found to comment on")
                    except Exception as e:
                        logger.error(f"Error posting commit comment: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                    
                    # If we couldn't comment on commit, try MR
                    if not comment_posted:
                        try:
                            merge_request = body.get("merge_request")
                            if merge_request:
                                mr_iid = merge_request.get("iid")
                                if mr_iid:
                                    # Check if the method is implemented
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
                    
                    # If all fails, at least we logged the analysis
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
        "ai": "vertex-ai-gemini-2.0-flash",
        "version": "1.0.0"
    }

@app.get("/stats")
async def get_stats():
    """Endpoint for statistics (future)"""
    return {
        "total_pipelines_analyzed": 0,
        "success_rate": 0,
        "ai_model": "gemini-2.0-flash-001"
    }

@app.get("/debug-token")
async def debug_token():
    """Endpoint for debugging GitLab token (development only)"""
    token = os.getenv("GITLAB_ACCESS_TOKEN", "")
    return {
        "token_present": bool(token),
        "token_length": len(token) if token else 0,
        "token_prefix": token[:4] + "..." if token else ""
    }