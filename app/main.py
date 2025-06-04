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
from app.vertex_ai_fixer import VertexAIFixer
from app.firestore_client import FirestoreClient
from app.ai_predictor import AIPredictor

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
vertex_fixer = VertexAIFixer(token=GITLAB_ACCESS_TOKEN)
firestore_client = FirestoreClient()
ai_predictor = AIPredictor()

# In-memory storage for analytics (backup when Firestore is down)
pipeline_analytics = []

# Cache for preventing duplicate processing
processed_pipelines = defaultdict(lambda: datetime.min)
created_mrs = defaultdict(list)

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("AI Pipeline Guardian starting up...")
    logger.info("🔮 Predictive analysis enabled")
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
            <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
            <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <style>
                :root {
                    --primary: #0F172A;
                    --secondary: #1E293B;
                    --accent: #3B82F6;
                    --success: #10B981;
                    --warning: #F59E0B;
                    --danger: #EF4444;
                    --text-primary: #F8FAFC;
                    --text-secondary: #CBD5E1;
                    --border: #334155;
                    --bg-card: #1E293B;
                    --bg-hover: #334155;
                }
                
                * {
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }
                
                body {
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
                    background: var(--primary);
                    color: var(--text-primary);
                    line-height: 1.6;
                    min-height: 100vh;
                }
                
                .container {
                    max-width: 1200px;
                    margin: 0 auto;
                    padding: 2rem;
                }
                
                .header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 3rem;
                    padding-bottom: 2rem;
                    border-bottom: 1px solid var(--border);
                }
                
                .logo {
                    display: flex;
                    align-items: center;
                    gap: 1rem;
                }
                
                .logo-icon {
                    width: 48px;
                    height: 48px;
                    background: var(--accent);
                    border-radius: 12px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 24px;
                }
                
                .logo-text h1 {
                    font-size: 1.875rem;
                    font-weight: 700;
                    margin: 0;
                }
                
                .logo-text p {
                    font-size: 0.875rem;
                    color: var(--text-secondary);
                    margin: 0;
                }
                
                .status-badge {
                    display: flex;
                    align-items: center;
                    gap: 0.5rem;
                    background: var(--bg-card);
                    padding: 0.75rem 1.5rem;
                    border-radius: 50px;
                    border: 1px solid var(--border);
                }
                
                .status-indicator {
                    width: 8px;
                    height: 8px;
                    background: var(--success);
                    border-radius: 50%;
                    animation: pulse 2s infinite;
                }
                
                @keyframes pulse {
                    0% { opacity: 1; }
                    50% { opacity: 0.5; }
                    100% { opacity: 1; }
                }
                
                .grid {
                    display: grid;
                    gap: 1.5rem;
                    margin-bottom: 2rem;
                }
                
                .stats-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 1rem;
                    margin-bottom: 2rem;
                }
                
                .stat-card {
                    background: var(--bg-card);
                    border: 1px solid var(--border);
                    border-radius: 12px;
                    padding: 1.5rem;
                    transition: all 0.3s ease;
                }
                
                .stat-card:hover {
                    border-color: var(--accent);
                    transform: translateY(-2px);
                }
                
                .stat-header {
                    display: flex;
                    align-items: center;
                    justify-content: space-between;
                    margin-bottom: 1rem;
                }
                
                .stat-icon {
                    width: 40px;
                    height: 40px;
                    background: rgba(59, 130, 246, 0.1);
                    border-radius: 8px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: var(--accent);
                }
                
                .stat-value {
                    font-size: 2rem;
                    font-weight: 700;
                    margin-bottom: 0.25rem;
                }
                
                .stat-label {
                    font-size: 0.875rem;
                    color: var(--text-secondary);
                }
                
                .card {
                    background: var(--bg-card);
                    border: 1px solid var(--border);
                    border-radius: 12px;
                    padding: 2rem;
                }
                
                .card-header {
                    display: flex;
                    align-items: center;
                    gap: 1rem;
                    margin-bottom: 1.5rem;
                }
                
                .card-icon {
                    width: 32px;
                    height: 32px;
                    background: rgba(59, 130, 246, 0.1);
                    border-radius: 8px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: var(--accent);
                }
                
                .card-title {
                    font-size: 1.25rem;
                    font-weight: 600;
                }
                
                .feature-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 1rem;
                    margin-bottom: 2rem;
                }
                
                .feature-card {
                    background: rgba(30, 41, 59, 0.5);
                    border: 1px solid var(--border);
                    border-radius: 8px;
                    padding: 1.5rem;
                    transition: all 0.3s ease;
                }
                
                .feature-card:hover {
                    background: var(--bg-hover);
                    border-color: var(--accent);
                }
                
                .feature-header {
                    display: flex;
                    align-items: center;
                    gap: 1rem;
                    margin-bottom: 0.75rem;
                }
                
                .feature-icon {
                    width: 32px;
                    height: 32px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: var(--accent);
                }
                
                .feature-title {
                    font-weight: 600;
                    font-size: 1rem;
                }
                
                .feature-description {
                    font-size: 0.875rem;
                    color: var(--text-secondary);
                    line-height: 1.5;
                }
                
                .endpoints-grid {
                    display: grid;
                    gap: 0.75rem;
                }
                
                .endpoint {
                    display: flex;
                    align-items: center;
                    gap: 1rem;
                    padding: 0.75rem 1rem;
                    background: rgba(30, 41, 59, 0.5);
                    border: 1px solid var(--border);
                    border-radius: 6px;
                    transition: all 0.3s ease;
                }
                
                .endpoint:hover {
                    background: var(--bg-hover);
                    border-color: var(--accent);
                }
                
                .method {
                    font-size: 0.75rem;
                    font-weight: 600;
                    padding: 0.25rem 0.5rem;
                    border-radius: 4px;
                    background: rgba(59, 130, 246, 0.2);
                    color: var(--accent);
                    min-width: 50px;
                    text-align: center;
                }
                
                .endpoint-path {
                    font-family: 'Monaco', 'Consolas', monospace;
                    font-size: 0.875rem;
                    color: var(--text-primary);
                }
                
                .endpoint-description {
                    margin-left: auto;
                    font-size: 0.875rem;
                    color: var(--text-secondary);
                }
                
                .dashboard-btn {
                    display: inline-flex;
                    align-items: center;
                    gap: 0.75rem;
                    background: var(--accent);
                    color: white;
                    padding: 1rem 2rem;
                    border-radius: 8px;
                    text-decoration: none;
                    font-weight: 600;
                    transition: all 0.3s ease;
                    margin-top: 2rem;
                }
                
                .dashboard-btn:hover {
                    background: #2563EB;
                    transform: translateY(-2px);
                    box-shadow: 0 10px 20px rgba(59, 130, 246, 0.3);
                }
                
                .tech-stack {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 0.5rem;
                    margin-top: 1rem;
                }
                
                .tech-badge {
                    display: inline-flex;
                    align-items: center;
                    gap: 0.5rem;
                    padding: 0.5rem 1rem;
                    background: rgba(30, 41, 59, 0.5);
                    border: 1px solid var(--border);
                    border-radius: 6px;
                    font-size: 0.875rem;
                }
                
                .tech-badge i {
                    color: var(--accent);
                }
                
                .prediction-banner {
                    background: linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(59, 130, 246, 0.1) 100%);
                    border: 1px solid rgba(168, 85, 247, 0.3);
                    border-radius: 12px;
                    padding: 1.5rem;
                    margin-bottom: 2rem;
                    text-align: center;
                }
                
                .prediction-banner h2 {
                    font-size: 1.5rem;
                    margin-bottom: 0.5rem;
                    color: #A855F7;
                }
                
                .prediction-banner p {
                    color: var(--text-secondary);
                }
            </style>
        </head>
        <body>
            <div class="container">
                <header class="header">
                    <div class="logo">
                        <div class="logo-icon">
                            <i class="fas fa-shield-alt"></i>
                        </div>
                        <div class="logo-text">
                            <h1>AI Pipeline Guardian</h1>
                            <p>Predictive CI/CD Failure Prevention</p>
                        </div>
                    </div>
                    <div class="status-badge">
                        <span class="status-indicator"></span>
                        <span>System Operational</span>
                    </div>
                </header>
                
                <div class="prediction-banner">
                    <h2>Now with Predictive Intelligence</h2>
                    <p>Prevent pipeline failures before they happen with AI-powered predictions</p>
                </div>

                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-eye"></i>
                            </div>
                        </div>
                        <div class="stat-value">Predictive</div>
                        <div class="stat-label">Failure Prevention Mode</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-robot"></i>
                            </div>
                        </div>
                        <div class="stat-value">5 + Predict</div>
                        <div class="stat-label">AI Capabilities</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-brain"></i>
                            </div>
                        </div>
                        <div class="stat-value">Gemini 2.0</div>
                        <div class="stat-label">AI Model (Vertex AI)</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-check-circle"></i>
                            </div>
                        </div>
                        <div class="stat-value">""" + ("Active" if GITLAB_ACCESS_TOKEN else "Missing") + """</div>
                        <div class="stat-label">GitLab Integration</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-database"></i>
                            </div>
                        </div>
                        <div class="stat-value">""" + ("Firestore" if firestore_client.db else "Memory") + """</div>
                        <div class="stat-label">Data Storage</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-header">
                            <div class="stat-icon">
                                <i class="fas fa-code-branch"></i>
                            </div>
                        </div>
                        <div class="stat-value">GraphQL</div>
                        <div class="stat-label">API Support</div>
                    </div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <div class="card-icon">
                            <i class="fas fa-magic"></i>
                        </div>
                        <h2 class="card-title">AI-Powered Capabilities</h2>
                    </div>
                    <div class="feature-grid">
                        <div class="feature-card" style="border-color: #A855F7;">
                            <div class="feature-header">
                                <div class="feature-icon" style="color: #A855F7;">
                                    <i class="fas fa-eye"></i>
                                </div>
                                <h3 class="feature-title">Predictive Failure Detection</h3>
                            </div>
                            <p class="feature-description">Analyzes historical patterns to predict pipeline failures before they occur</p>
                        </div>
                        <div class="feature-card">
                            <div class="feature-header">
                                <div class="feature-icon">
                                    <i class="fas fa-cube"></i>
                                </div>
                                <h3 class="feature-title">Dependency Resolution</h3>
                            </div>
                            <p class="feature-description">Automatically detects missing packages and creates MRs to add them</p>
                        </div>
                        <div class="feature-card">
                            <div class="feature-header">
                                <div class="feature-icon">
                                    <i class="fas fa-code"></i>
                                </div>
                                <h3 class="feature-title">Syntax Error Correction</h3>
                            </div>
                            <p class="feature-description">Fixes common syntax errors across 9 programming languages</p>
                        </div>
                        <div class="feature-card">
                            <div class="feature-header">
                                <div class="feature-icon">
                                    <i class="fas fa-clock"></i>
                                </div>
                                <h3 class="feature-title">Timeout Optimization</h3>
                            </div>
                            <p class="feature-description">Increases job timeouts when jobs exceed time limits</p>
                        </div>
                        <div class="feature-card">
                            <div class="feature-header">
                                <div class="feature-icon">
                                    <i class="fas fa-shield-alt"></i>
                                </div>
                                <h3 class="feature-title">Security Updates</h3>
                            </div>
                            <p class="feature-description">Updates vulnerable packages to secure versions when CVEs are detected</p>
                        </div>
                        <div class="feature-card">
                            <div class="feature-header">
                                <div class="feature-icon">
                                    <i class="fas fa-chart-line"></i>
                                </div>
                                <h3 class="feature-title">Pattern Learning</h3>
                            </div>
                            <p class="feature-description">Learns from failure patterns across your organization</p>
                        </div>
                    </div>
                </div>

                <div class="grid" style="grid-template-columns: 1fr 1fr; gap: 2rem;">
                    <div class="card">
                        <div class="card-header">
                            <div class="card-icon">
                                <i class="fas fa-plug"></i>
                            </div>
                            <h2 class="card-title">API Endpoints</h2>
                        </div>
                        <div class="endpoints-grid">
                            <div class="endpoint">
                                <span class="method">GET</span>
                                <span class="endpoint-path">/health</span>
                                <span class="endpoint-description">Health check</span>
                            </div>
                            <div class="endpoint">
                                <span class="method">GET</span>
                                <span class="endpoint-path">/dashboard</span>
                                <span class="endpoint-description">Analytics dashboard</span>
                            </div>
                            <div class="endpoint">
                                <span class="method">GET</span>
                                <span class="endpoint-path">/stats</span>
                                <span class="endpoint-description">Raw statistics</span>
                            </div>
                            <div class="endpoint">
                                <span class="method">POST</span>
                                <span class="endpoint-path">/webhook</span>
                                <span class="endpoint-description">GitLab webhook</span>
                            </div>
                            <div class="endpoint">
                                <span class="method">POST</span>
                                <span class="endpoint-path">/predict</span>
                                <span class="endpoint-description">Predict failure</span>
                            </div>
                            <div class="endpoint">
                                <span class="method">POST</span>
                                <span class="endpoint-path">/analyze</span>
                                <span class="endpoint-description">Manual analysis</span>
                            </div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <div class="card-header">
                            <div class="card-icon">
                                <i class="fas fa-layer-group"></i>
                            </div>
                            <h2 class="card-title">Technology Stack</h2>
                        </div>
                        <div class="tech-stack">
                            <div class="tech-badge">
                                <i class="fab fa-python"></i>
                                <span>Python 3.11</span>
                            </div>
                            <div class="tech-badge">
                                <i class="fab fa-google"></i>
                                <span>Vertex AI</span>
                            </div>
                            <div class="tech-badge">
                                <i class="fas fa-cloud"></i>
                                <span>Cloud Run</span>
                            </div>
                            <div class="tech-badge">
                                <i class="fab fa-gitlab"></i>
                                <span>GitLab API</span>
                            </div>
                            <div class="tech-badge">
                                <i class="fas fa-code-branch"></i>
                                <span>GraphQL</span>
                            </div>
                            <div class="tech-badge">
                                <i class="fas fa-database"></i>
                                <span>Firestore</span>
                            </div>
                            <div class="tech-badge">
                                <i class="fab fa-docker"></i>
                                <span>Docker</span>
                            </div>
                        </div>
                    </div>
                </div>
                
                <a href="/dashboard" class="dashboard-btn">
                    <i class="fas fa-chart-line"></i>
                    View Analytics Dashboard
                </a>
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
        
        # NEW: Handle running pipelines for prediction
        if status == "running":
            project = body.get("project", {})
            project_id = project.get("id")
            project_name = project.get("name")
            project_path = project.get("path_with_namespace")
            pipeline_id = object_attributes.get("id")
            ref = object_attributes.get("ref", "unknown")
            
            logger.info(f"🔮 Pipeline {pipeline_id} started - analyzing risk...")
            
            try:
                # Get historical data via GraphQL
                if project_path:
                    historical_stats = await gitlab_client.get_project_statistics_graphql(project_path)
                    historical_pipelines = await gitlab_client.get_project_pipelines_graphql(project_path, last_n=50)
                    
                    # Analyze patterns
                    pattern_analysis = ai_predictor.analyze_failure_patterns(historical_pipelines)
                    
                    # Count recent commits (simplified - you could enhance this)
                    recent_commits = len(body.get("commits", []))
                    
                    # Predict failure risk
                    current_pipeline = {
                        "id": pipeline_id,
                        "ref": ref,
                        "status": status,
                        "created_at": object_attributes.get("created_at")
                    }
                    
                    prediction = ai_predictor.predict_failure_risk(
                        current_pipeline=current_pipeline,
                        historical_data=pattern_analysis,
                        recent_commits=recent_commits
                    )
                    
                    logger.info(f"Risk Score: {prediction['risk_score']} ({prediction['risk_level']})")
                    
                    # If high risk, create preventive issue
                    if prediction['risk_score'] >= 0.7:
                        issue_title = f"⚠️ High Risk Alert: Pipeline #{pipeline_id} likely to fail"
                        issue_description = ai_predictor.get_predictive_comment(prediction, project_name)
                        
                        issue = await gitlab_client.create_issue(
                            project_id=project_id,
                            title=issue_title,
                            description=issue_description
                        )
                        
                        if issue:
                            logger.info(f"✅ Created preventive issue #{issue.get('iid')}")
                            
                            # Store prediction in Firestore
                            await firestore_client.save_pipeline_analysis({
                                "pipeline_id": pipeline_id,
                                "project_id": project_id,
                                "project_name": project_name,
                                "timestamp": datetime.now(),
                                "prediction": prediction,
                                "issue_created": issue.get('iid'),
                                "type": "prediction"
                            })
                    
                    return {
                        "status": "predicted",
                        "risk_score": prediction['risk_score'],
                        "risk_level": prediction['risk_level'],
                        "insights": pattern_analysis.get('insights', [])
                    }
                
            except Exception as e:
                logger.error(f"Error in predictive analysis: {e}")
                # Continue with normal processing
        
        # Only process failed pipelines that are complete
        if status != "failed":
            logger.info(f"Pipeline status is '{status}', skipping failure analysis")
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
                
                # Enhanced analysis with Vertex AI for specific error types
                mr_created = False
                vertex_enhanced = False
                
                if analysis['error_category'] in ['dependency', 'syntax_error', 'timeout', 'security', 'configuration']:
                    logger.info("🧠 Enhancing analysis with Vertex AI...")
                    
                    # Extract error details
                    error_details = analysis.get('error_details', {})
                    error_details['language'] = analysis.get('language', 'python')
                    
                    # For dependency errors
                    if analysis['error_category'] == 'dependency':
                        module_name = error_details.get('missing_module')
                        if not module_name:
                            # Language-specific extraction
                            language = error_details.get('language', 'python')
                            if language == 'python' and 'ModuleNotFoundError' in job_log:
                                match = re.search(r"No module named '([^']+)'", job_log)
                                if match:
                                    module_name = match.group(1)
                                    error_details['missing_module'] = module_name
                            elif language == 'javascript' and 'Cannot find module' in job_log:
                                match = re.search(r"Cannot find module '([^']+)'", job_log)
                                if match:
                                    module_name = match.group(1)
                                    error_details['missing_module'] = module_name
                    
                    # Check if we already created an MR for this error
                    mr_key = f"{project_id}:{analysis['error_category']}:{json.dumps(error_details, sort_keys=True)}"
                    existing_mrs = created_mrs[mr_key]
                    
                    if existing_mrs:
                        recent_mr = existing_mrs[-1]
                        if datetime.now() - recent_mr['timestamp'] < timedelta(hours=1):
                            logger.info(f"MR already created for this error: {recent_mr['url']}")
                            analysis['mr_url'] = recent_mr['url']
                            analysis['mr_exists'] = True
                            mr_created = False
                        else:
                            mr_created = True
                    else:
                        mr_created = True
                    
                    if mr_created and analysis['recommended_action'] == 'automatic_fix':
                        # Get AI-powered fix suggestion
                        fix_suggestion = await vertex_fixer.suggest_fix(
                            project_id=project_id,
                            error_type=analysis['error_category'],
                            error_details=error_details,
                            job_log=job_log
                        )
                        
                        if fix_suggestion.get('success'):
                            # Prepare fix data
                            fix_data = {
                                'error_type': analysis['error_category'],
                                'pipeline_id': pipeline_id,
                                'job_name': job_name,
                                'error_explanation': analysis['error_explanation'],
                                'analysis_confidence': 95,
                                'explanation': fix_suggestion.get('explanation'),
                                'confidence': fix_suggestion.get('confidence', 85),
                                'language': analysis.get('language', 'python'),
                                **error_details  # Include all extracted error details
                            }
                            
                            # Try to create auto-fix MR
                            logger.info(f"Creating auto-fix MR for {analysis['error_category']} error")
                            mr_result = await vertex_fixer.create_fix_mr(
                                gitlab_client=gitlab_client,
                                project_id=project_id,
                                source_branch=ref,
                                fix_data=fix_data
                            )
                            
                            if mr_result.get('success'):
                                mr_created = True
                                mr_count += 1
                                logger.info(f"✅ Created MR: {mr_result['mr_url']}")
                                # Track this MR
                                created_mrs[mr_key].append({
                                    'url': mr_result['mr_url'],
                                    'timestamp': datetime.now()
                                })
                                # Update analysis with MR info
                                analysis['mr_url'] = mr_result['mr_url']
                                analysis['mr_created'] = True
                                vertex_enhanced = True
                            else:
                                mr_created = False
                                logger.error(f"Failed to create MR: {mr_result.get('error')}")
                
                # Store analysis result
                analysis_result = {
                    "job_name": job_name,
                    "job_id": job_id,
                    "error_category": analysis['error_category'],
                    "recommended_action": analysis['recommended_action'],
                    "timestamp": datetime.now().isoformat(),
                    "vertex_enhanced": vertex_enhanced,
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
                language = analysis.get('language', 'python')
                comment = f"""🤖 **AI Pipeline Guardian Analysis**

**Pipeline:** #{pipeline_id} on `{ref}`
**Job:** `{job_name}`
**Language:** `{language.upper()}`
**Status:** Failed ❌

**🔍 Error Analysis:**
{analysis['error_explanation']}

**📁 Category:** `{analysis['error_category']}`
**🎯 Recommended Action:** `{analysis['recommended_action']}`

**💡 Suggested Solution:**
{analysis['suggested_solution']}"""

                # Add Vertex AI enhancement if available
                if vertex_enhanced:
                    comment += f"""

**🧠 Google Vertex AI Enhancement:**
AI-powered automatic fix has been implemented using Gemini 2.0 Flash."""

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
*This analysis was generated automatically by AI Pipeline Guardian*
*Powered by Google Cloud Vertex AI (Gemini 2.0 Flash)*"""
                
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
            # Get commit SHA if available
            commit_sha = None
            commits = body.get("commits", [])
            if commits:
                commit_sha = commits[-1].get("id")
            
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
                "vertex_enhanced": any(a.get('vertex_enhanced') for a in analyses),
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

@app.post("/predict/{project_id}/{pipeline_id}")
async def predict_pipeline_failure(project_id: int, pipeline_id: int):
    """Manual endpoint to predict pipeline failure risk"""
    try:
        # Get project path (you might need to get this from GitLab API)
        project_path = f"user/project"  # This should be fetched from GitLab
        
        # Get historical data
        historical_stats = await gitlab_client.get_project_statistics_graphql(project_path)
        historical_pipelines = await gitlab_client.get_project_pipelines_graphql(project_path, last_n=100)
        
        # Analyze patterns
        pattern_analysis = ai_predictor.analyze_failure_patterns(historical_pipelines)
        
        # Get current pipeline details
        current_pipeline = await gitlab_client.get_pipeline_details(project_id, pipeline_id)
        
        # Predict
        prediction = ai_predictor.predict_failure_risk(
            current_pipeline=current_pipeline,
            historical_data=pattern_analysis,
            recent_commits=0  # You could fetch this
        )
        
        return {
            "prediction": prediction,
            "patterns": pattern_analysis,
            "statistics": historical_stats
        }
        
    except Exception as e:
        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
        "vertex_ai": "enabled",
        "ai_model": "gemini-2.0-flash",
        "version": "4.0.0",
        "token_configured": bool(GITLAB_ACCESS_TOKEN),
        "loop_protection": "active",
        "firestore_connected": bool(firestore_client.db),
        "auto_fix_types": ["dependency", "syntax_error", "timeout", "security", "configuration"],
        "supported_languages": ["python", "javascript", "java", "go", "ruby", "php", "rust", "csharp", "typescript"],
        "predictive_analysis": "enabled",
        "graphql_support": "enabled"
    }

@app.get("/stats")
async def get_stats():
    """Raw statistics API endpoint"""
    if firestore_client.db:
        # Get stats from Firestore
        stats = await firestore_client.get_dashboard_stats()
        stats["predictions_enabled"] = True
        stats["graphql_queries"] = True
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
        
        # Vertex AI usage stats
        vertex_enhanced_count = sum(1 for p in pipeline_analytics 
                                   for a in p.get('analyses', []) 
                                   if a.get('vertex_enhanced'))
        
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
            "vertex_ai_enhanced_analyses": vertex_enhanced_count,
            "success_rate": round(sum(p.get('retried_jobs', 0) for p in pipeline_analytics) / max(total_pipelines, 1) * 100, 1),
            "error_categories": categories,
            "recent_analyses": pipeline_analytics[-10:] if pipeline_analytics else [],
            "hourly_rate_saved": total_time_saved * 60 / 60,
            "loop_protection_active": True,
            "recent_pipelines_processed": recent_pipelines,
            "data_source": "memory",
            "ai_technology": "Google Vertex AI - Gemini 2.0 Flash",
            "auto_fix_capabilities": {
                "dependency": "Adds missing modules to requirements.txt",
                "syntax_error": "Fixes Python syntax errors",
                "timeout": "Increases job timeout in CI config",
                "security": "Updates vulnerable packages",
                "configuration": "Creates .env.example for missing vars"
            },
            "predictions_enabled": True,
            "graphql_queries": True
        }

# Add endpoint for pipeline start (component compatibility)
@app.post("/pipeline/start")
async def pipeline_start(request: Request):
    """Track pipeline starts (optional)"""
    body = await request.json()
    logger.info(f"Pipeline started: {body.get('pipeline_id')}")
    return {"status": "acknowledged"}