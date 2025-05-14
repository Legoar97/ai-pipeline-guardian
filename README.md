# AI Pipeline Guardian

**AI-Powered CI/CD Failure Diagnosis and Remediation for GitLab Pipelines**

AI Pipeline Guardian is an advanced monitoring solution that oversees GitLab continuous integration and deployment pipelines, detects failures in real-time, analyzes logs using Google Cloud's Vertex AI, and executes automated corrective actions to retry processes, implement solutions, or recommend remediation—enabling development teams to increase productivity and minimize workflow disruptions.

## Key Features

- **Real-time monitoring** of GitLab pipelines via webhooks
- **In-depth root cause analysis** powered by Vertex AI (Gemini/PaLM)
- **Automatic retry capability** for transient or unstable jobs
- **Self-healing automation** for common issues (formatting, missing imports)
- **Intelligent merge request comments** with cause identification and resolution suggestions
- **Analytical dashboard** for incident visualization and corrective action tracking
- **Optional GitLab OAuth integration** for project configuration

## Technology Stack

- **Python 3.11** with FastAPI backend
- **Google Cloud Platform**
  - Vertex AI for language model-based analysis
  - Cloud Run for serverless deployment
  - Secret Manager for secure token storage
  - Firestore/BigQuery (optional) for data persistence
- **GitLab**
  - REST and GraphQL APIs
  - CI/CD integration and webhook system
- **Docker** for containerization and deployment

## Project Objectives

This project was developed for the [Google Cloud + GitLab Hackathon 2025](https://ai-in-action.devpost.com) with the aim of addressing a common DevOps challenge:

> "CI/CD failures disrupt developer flow. What if an artificial intelligence could detect, explain, and fix these failures before the developer needs to review the logs?"

## How It Works

1. GitLab sends a webhook notification when a pipeline fails
2. The system retrieves job logs through the GitLab API
3. Logs are processed with Vertex AI for detailed error analysis
4. Based on the analysis, the system:
   - Retries job execution (for transient issues)
   - Fixes code (formatting, missing dependencies)
   - Adds comments to merge requests with diagnostics and recommendations
5. All activity is recorded in a dashboard for tracking

## Current Status

**In active development for the hackathon.**  
Public release and complete documentation will be available before the submission deadline (June 17, 2025).

## License

MIT License — see the [`LICENSE`](LICENSE) file for details.
