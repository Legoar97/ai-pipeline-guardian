from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import json
import os
import logging
import asyncio
import re
from typing import Dict, List
from datetime import datetime, timedelta
from collections import defaultdict
from app.gitlab_client import GitLabClient
from app.ai_analyzer import AIAnalyzer
from app.duo_client import GitLabDuoClient
from app.firestore_client import FirestoreClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Pipeline Guardian")

# Templates for dashboard
templates = Jinja2Templates(directory="app/templates")

# Environment variables
GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET", "")
GITLAB_ACCESS_TOKEN = os.getenv("GITLAB_ACCESS_TOKEN", "")

# Initialize clients
gitlab_client = GitLabClient(token=GITLAB_ACCESS_TOKEN)
ai_analyzer = AIAnalyzer()
duo_client = GitLabDuoClient(token=GITLAB_ACCESS_TOKEN)
firestore_client = FirestoreClient()

# In-memory storage for analytics (backup when Firestore is down)
pipeline_analytics = []

# Cache for preventing duplicate processing
processed_pipelines = defaultdict(lambda: datetime.min)
created_mrs = defaultdict(list)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("AI Pipeline Guardian starting up...")
    # Clean up old data (older than 30 days)
    if firestore_client.db:
        await firestore_client.cleanup_old_data(30)

@app.get("/", response_class=HTMLResponse)
async def root():
    """Home page with service status"""
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
                .badge-duo { background-color: #ff6b6b; color: white; }
                .stats { display: flex; justify-content: space-around; margin: 20px 0; }
                .stat-box { text-align: center; padding: 15px; background: #f8f9fa; border-radius: 8px; }
                .stat-value { font-size: 2em; font-weight: bold; color: #7c3aed; }
                .stat-label { color: #666; font-size: 0.9em; }
                .protection { background: #d4edda; color: #155724; padding: 10px; border-radius: 5px; margin: 10px 0; }
                .dashboard-link { display: inline-block; margin-top: 20px; padding: 12px 24px; background: #7c3aed; color: white; text-decoration: none; border-radius: 8px; font-weight: bold; }
                .dashboard-link:hover { background: #6d28d9; color: white; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 AI Pipeline Guardian <span class="badge badge-ai">AI-Powered</span> <span class="badge badge-duo">Duo Enhanced</span></h1>
                <p class="status">Status: Active <span class="badge badge-ready">Ready</span></p>
                
                <div class="protection">
                    ✅ <strong>Loop Protection Active:</strong> Duplicate pipeline processing prevented<br>
                    ✅ <strong>Firestore Connected:</strong> """ + ("Yes" if firestore_client.db else "No") + """
                </div>
                
                <div class="info">
                    <h3>Configuration</h3>
                    <p><strong>Webhook URL:</strong> <code>POST /webhook</code></p>
                    <p><strong>Dashboard:</strong> <code>GET /dashboard</code></p>
                    <p><strong>GitLab Events:</strong> Pipeline Hook</p>
                    <p><strong>AI Model:</strong> Vertex AI (Gemini 2.0 Flash) 🧠</p>
                    <p><strong>GitLab Duo:</strong> <span class="badge badge-duo">Enabled</span> 🚀</p>
                    <p><strong>Access Token:</strong> """ + ("✅ Configured" if GITLAB_ACCESS_TOKEN else "❌ Missing") + """</p>
                    <p><strong>Data Persistence:</strong> """ + ("✅ Firestore" if firestore_client.db else "⚠️ In-Memory Only") + """</p>
                    
                    <h3>Features</h3>
                    <div class="feature">Automatic failure analysis with AI</div>
                    <div class="feature">Smart retry for transient errors</div>
                    <div class="feature">GitLab Duo integration for code fixes</div>
                    <div class="feature">Auto-generated MRs with fixes</div>
                    <div class="feature">Intelligent comments on commits</div>
                    <div class="feature">Real-time analytics dashboard</div>
                    <div class="feature">Loop prevention system</div>
                    <div class="feature">Persistent data storage with Firestore</div>
                    
                    <h3>API Endpoints</h3>
                    <p><code>GET /health</code> - Health check</p>
                    <p><code>GET /dashboard</code> - Analytics dashboard</p>
                    <p><code>GET /stats</code> - Raw statistics API</p>
                    <p><code>POST /webhook</code> - GitLab webhook receiver</p>
                    <p><code>POST /analyze</code> - Manual analysis trigger</p>
                </div>
                
                <a href="/dashboard" class="dashboard-link">View Analytics Dashboard →</a>
            </div>
        </body>
    </html>
    """

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Analytics dashboard with real-time stats from Firestore"""
    try:
        # Get stats from Firestore
        stats = await firestore_client.get_dashboard_stats()
        
        # Format timestamp
        last_update = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "stats": stats,
            "last_update": last_update
        })
    except Exception as e:
        logger.error(f"Error rendering dashboard: {e}")
        raise HTTPException(status_code=500, detail="Dashboard error")

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
        
        # Only process failed pipelines that are complete
        if status != "failed":
            logger.info(f"Pipeline status is '{status}', skipping")
            return {"status": "skipped", "reason": f"Pipeline status is {status}"}
        
        project = body.get("project", {})
        project_id = project.get("id")
        project_name = project.get("name")
        pipeline_id = object_attributes.get("id")
        ref = object_attributes.get("ref", "unknown")
        
        # Check if we processed this pipeline recently
        last_processed = processed_pipelines[pipeline_id]
        if datetime.now() - last_processed < timedelta(minutes=10):
            time_since = datetime.now() - last_processed
            logger.info(f"Pipeline {pipeline_id} was processed {time_since} ago, skipping")
            return {"status": "skipped", "reason": "recently_processed", "last_processed": str(time_since)}
        
        # Mark as processed
        processed_pipelines[pipeline_id] = datetime.now()
        
        logger.info(f"Pipeline failed! Project: {project_name}, Pipeline ID: {pipeline_id}, Branch: {ref}")
        
        # Wait a bit for GitLab to register all job statuses
        logger.info("Waiting for job statuses to stabilize...")
        await asyncio.sleep(5)
        
        # Analyze the failure with AI
        try:
            # Get jobs from the pipeline
            jobs = await gitlab_client.get_pipeline_jobs(project_id, pipeline_id)
            
            # Find failed jobs
            failed_jobs = [job for job in jobs if job.get("status") == "failed"]
            logger.info(f"Found {len(failed_jobs)} failed jobs")
            
            if not failed_jobs:
                # Try again after another delay
                logger.info("No failed jobs found, waiting and retrying...")
                await asyncio.sleep(3)
                jobs = await gitlab_client.get_pipeline_jobs(project_id, pipeline_id)
                failed_jobs = [job for job in jobs if job.get("status") == "failed"]
                logger.info(f"After retry: Found {len(failed_jobs)} failed jobs")
            
            analyzed_count = 0
            retry_count = 0
            comment_count = 0
            mr_count = 0
            analyses = []
            
            for job in failed_jobs:
                job_id = job.get("id")
                job_name = job.get("name")
                
                # Skip GitLab system jobs
                if job_name and job_name.startswith("ai_guardian:"):
                    continue
                
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
                
                # Track error pattern in Firestore
                await firestore_client.save_error_pattern(
                    analysis['error_category'],
                    {
                        'job_name': job_name,
                        'error': analysis['error_explanation'],
                        'solution': analysis['suggested_solution'],
                        'project': project_name,
                        'timestamp': datetime.now()
                    }
                )
                
                # Enhanced analysis with Duo for specific error types
                mr_created = False
                duo_enhanced = False
                
                if analysis['error_category'] in ['dependency', 'syntax_error']:
                    logger.info("🧠 Enhancing analysis with GitLab Duo...")
                    
                    # Extract module name for dependency errors
                    module_name = None
                    if analysis['error_category'] == 'dependency' and 'ModuleNotFoundError' in job_log:
                        # Extract module name from error
                        match = re.search(r"No module named '([^']+)'", job_log)
                        if match:
                            module_name = match.group(1)
                            logger.info(f"Detected missing module: {module_name}")
                    
                    # Check if we already created an MR for this type of error in this project
                    existing_mrs = created_mrs[f"{project_id}:{analysis['error_category']}:{module_name}"]
                    if existing_mrs:
                        recent_mr = existing_mrs[-1]
                        if datetime.now() - recent_mr['timestamp'] < timedelta(hours=1):
                            logger.info(f"MR already created for this error: {recent_mr['url']}")
                            analysis['mr_url'] = recent_mr['url']
                            analysis['mr_exists'] = True
                            mr_created = False
                        else:
                            # Create new MR if the last one is old
                            mr_created = True
                    else:
                        mr_created = True
                    
                    if mr_created:
                        duo_result = await duo_client.suggest_fix(
                            project_id=project_id,
                            error_type=analysis['error_category'],
                            error_details={
                                'module': module_name,
                                'error_line': job_log.split('\n')[-5] if analysis['error_category'] == 'syntax_error' else '',
                                'error_explanation': analysis['error_explanation'],
                                'job_name': job_name,
                                'pipeline_id': pipeline_id
                            }
                        )
                        
                        duo_enhanced = duo_result.get('success', False)
                        
                        # If Duo has high confidence, create an MR
                        if duo_result.get('success') and duo_result.get('confidence', 0) > 0.85:
                            logger.info(f"🚀 Duo suggests fix with {duo_result['confidence']*100}% confidence")
                            
                            # Auto-create MR for dependency errors
                            if analysis['error_category'] == 'dependency' and module_name:
                                logger.info(f"Creating auto-fix MR for missing module: {module_name}")
                                mr_result = await duo_client.create_fix_mr(
                                    gitlab_client=gitlab_client,
                                    project_id=project_id,
                                    source_branch=ref,
                                    fix_data={
                                        'error_type': 'dependency',
                                        'module': module_name,
                                        'pipeline_id': pipeline_id,
                                        'job_name': job_name,
                                        'error_explanation': analysis['error_explanation'],
                                        'explanation': duo_result['explanation'],
                                        'confidence': duo_result['confidence'],
                                        'analysis_confidence': 95,
                                        'fix_description': f"Add {module_name} to requirements.txt"
                                    }
                                )
                                
                                if mr_result.get('success'):
                                    mr_created = True
                                    mr_count += 1
                                    logger.info(f"✅ Created MR: {mr_result['mr_url']}")
                                    # Track this MR
                                    created_mrs[f"{project_id}:{analysis['error_category']}:{module_name}"].append({
                                        'url': mr_result['mr_url'],
                                        'timestamp': datetime.now()
                                    })
                                    # Update analysis with MR info
                                    analysis['mr_url'] = mr_result['mr_url']
                                    analysis['mr_created'] = True
                                else:
                                    mr_created = False
                
                # Store analysis result
                analysis_result = {
                    "job_name": job_name,
                    "job_id": job_id,
                    "error_category": analysis['error_category'],
                    "recommended_action": analysis['recommended_action'],
                    "timestamp": datetime.now().isoformat(),
                    "duo_enhanced": duo_enhanced,
                    "mr_created": mr_created
                }
                analyses.append(analysis_result)
                
                # Take action based on analysis
                if analysis["recommended_action"] == "retry" and analysis["error_category"] in ["transient", "network", "timeout"]:
                    logger.info(f"AI recommends retry for transient error in job {job_name}")
                    if GITLAB_ACCESS_TOKEN:
                        success = await gitlab_client.retry_job(project_id, job_id)
                        if success:
                            retry_count += 1
                            analysis_result["retry_success"] = True
                            logger.info(f"Successfully retried job {job_name}")
                    else:
                        logger.warning("No GitLab token configured for retry")

                # Create a comment with the analysis
                comment = f"""🤖 **AI Pipeline Guardian Analysis**

**Pipeline:** #{pipeline_id} on `{ref}`
**Job:** `{job_name}`
**Status:** Failed ❌

**🔍 Error Analysis:**
{analysis['error_explanation']}

**📁 Category:** `{analysis['error_category']}`
**🎯 Recommended Action:** `{analysis['recommended_action']}`

**💡 Suggested Solution:**
{analysis['suggested_solution']}"""

                # Add Duo enhancement if available
                if duo_enhanced:
                    comment += f"""

**🧠 GitLab Duo Enhancement:**
AI confidence: {duo_result.get('confidence', 0)*100:.0f}%
{duo_result.get('explanation', '')}"""

                # Add MR link if created or exists
                if 'mr_url' in analysis:
                    if analysis.get('mr_exists'):
                        comment += f"""

### 🔄 Existing Fix Available

**Merge Request**: {analysis['mr_url']}
**Status**: Please review and merge the existing MR to resolve this issue."""
                    else:
                        comment += f"""

### 🎯 Automatic Fix Generated!

**Merge Request**: {analysis['mr_url']}
**Status**: Ready for review

The AI has created a merge request with the necessary fix. Please review and merge to resolve this issue."""

                comment += """

---
*This analysis was generated automatically by AI Pipeline Guardian with GitLab Duo*"""
                
                # Try to comment (only once per pipeline)
                if GITLAB_ACCESS_TOKEN and comment_count == 0:  # Only comment once
                    # Get commit SHA from pipeline or webhook
                    commit_sha = None
                    
                    # Try webhook commits first
                    commits = body.get("commits", [])
                    if commits:
                        commit_sha = commits[-1].get("id")
                    
                    # If no commit in webhook, get from pipeline
                    if not commit_sha:
                        pipeline_details = await gitlab_client.get_pipeline_details(project_id, pipeline_id)
                        commit_sha = pipeline_details.get("sha")
                    
                    if commit_sha:
                        success = await gitlab_client.create_commit_comment(
                            project_id, commit_sha, comment
                        )
                        if success:
                            comment_count += 1
                            logger.info(f"Posted comment to commit {commit_sha[:8]}")
                else:
                    logger.info("Skipping additional comments to avoid spam")
            
            # Store complete analysis in Firestore
            pipeline_data = {
                "pipeline_id": pipeline_id,
                "project_id": project_id,
                "project_name": project_name,
                "ref": ref,
                "timestamp": datetime.now(),
                "failed_jobs": len(failed_jobs),
                "analyzed_jobs": analyzed_count,
                "retried_jobs": retry_count,
                "comments_posted": comment_count,
                "mrs_created": mr_count,
                "analyses": analyses,
                "time_saved": analyzed_count * 5 + retry_count * 10 + mr_count * 20,
                "mr_created": mr_count > 0,
                "retry_success": retry_count > 0,
                "commit_sha": commit_sha,
                "webhook_data": {
                    "event": x_gitlab_event,
                    "user": body.get("user", {}).get("name", "Unknown")
                }
            }
            
            # Save to Firestore
            await firestore_client.save_pipeline_analysis(pipeline_data)
            
            # Also keep in memory as backup
            pipeline_analytics.append(pipeline_data)
            
            summary = {
                "status": "analyzed",
                "action": "AI analysis complete",
                "pipeline_id": pipeline_id,
                "jobs_analyzed": analyzed_count,
                "jobs_retried": retry_count,
                "comments_posted": comment_count,
                "mrs_created": mr_count,
                "duo_enhanced": any(a.get('duo_enhanced') for a in analyses),
                "analyses": analyses,
                "saved_to_firestore": bool(firestore_client.db)
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

@app.post("/analyze")
async def manual_analyze(request: Request):
    """Endpoint for manual analysis from CI/CD component"""
    body = await request.json()
    
    pipeline_id = body.get("pipeline", {}).get("id")
    project_id = body.get("project", {}).get("id")
    
    if not pipeline_id or not project_id:
        raise HTTPException(status_code=400, detail="Missing pipeline or project ID")
    
    logger.info(f"Manual analysis requested for pipeline {pipeline_id}")
    
    # Simulate webhook call
    webhook_body = {
        "object_attributes": {"status": "failed", "id": pipeline_id, "ref": "main"},
        "project": {"id": project_id, "name": body.get("project", {}).get("name", "Unknown")}
    }
    
    # Process as webhook
    return await gitlab_webhook(
        Request("POST", "/webhook", headers={"X-Gitlab-Event": "Pipeline Hook"}, json=webhook_body),
        x_gitlab_token=GITLAB_WEBHOOK_SECRET,
        x_gitlab_event="Pipeline Hook"
    )

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "ai-pipeline-guardian",
        "ai": "vertex-ai-gemini-2.0-flash",
        "duo": "enabled",
        "version": "3.0.0",
        "token_configured": bool(GITLAB_ACCESS_TOKEN),
        "loop_protection": "active",
        "firestore_connected": bool(firestore_client.db)
    }

@app.get("/stats")
async def get_stats():
    """Raw statistics API endpoint"""
    if firestore_client.db:
        # Get stats from Firestore
        stats = await firestore_client.get_dashboard_stats()
        return stats
    else:
        # Fallback to in-memory stats
        total_pipelines = len(pipeline_analytics)
        total_time_saved = sum(p.get('time_saved', 0) for p in pipeline_analytics)
        
        # Category breakdown
        categories = {}
        for pipeline in pipeline_analytics:
            for analysis in pipeline.get('analyses', []):
                cat = analysis.get('error_category', 'other')
                categories[cat] = categories.get(cat, 0) + 1
        
        # Duo usage stats
        duo_enhanced_count = sum(1 for p in pipeline_analytics 
                                for a in p.get('analyses', []) 
                                if a.get('duo_enhanced'))
        
        # Recent pipelines processed
        recent_pipelines = []
        for pid, timestamp in list(processed_pipelines.items())[-5:]:
            recent_pipelines.append({
                "pipeline_id": pid,
                "processed_at": timestamp.isoformat(),
                "time_ago": str(datetime.now() - timestamp)
            })
        
        return {
            "total_pipelines_analyzed": total_pipelines,
            "total_jobs_analyzed": sum(p.get('analyzed_jobs', 0) for p in pipeline_analytics),
            "total_jobs_retried": sum(p.get('retried_jobs', 0) for p in pipeline_analytics),
            "total_mrs_created": sum(p.get('mrs_created', 0) for p in pipeline_analytics),
            "total_time_saved_minutes": total_time_saved,
            "duo_enhanced_analyses": duo_enhanced_count,
            "success_rate": round(sum(p.get('retried_jobs', 0) for p in pipeline_analytics) / max(total_pipelines, 1) * 100, 1),
            "error_categories": categories,
            "recent_analyses": pipeline_analytics[-10:] if pipeline_analytics else [],
            "hourly_rate_saved": total_time_saved * 60 / 60,
            "loop_protection_active": True,
            "recent_pipelines_processed": recent_pipelines,
            "data_source": "memory"
        }

# Add endpoint for pipeline start (component compatibility)
@app.post("/pipeline/start")
async def pipeline_start(request: Request):
    """Track pipeline starts (optional)"""
    body = await request.json()
    logger.info(f"Pipeline started: {body.get('pipeline_id')}")
    return {"status": "acknowledged"}