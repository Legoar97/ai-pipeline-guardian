import os
import aiohttp
from typing import Dict, List, Optional
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class GitLabClient:
    def __init__(self, gitlab_url: str = "https://gitlab.com", token: Optional[str] = None):
        self.gitlab_url = gitlab_url
        self.token = token or os.getenv("GITLAB_ACCESS_TOKEN", "")
        self.headers = {}
        if self.token:
            self.headers["PRIVATE-TOKEN"] = self.token
            # Also add alternative authorization header for some endpoints
            self.headers["Authorization"] = f"Bearer {self.token}"
        logger.info(f"GitLab client initialized. Token present: {'Yes' if self.token else 'No'}")
    
    async def graphql_query(self, query: str, variables: Dict = None) -> Dict:
        """Execute GraphQL query against GitLab"""
        url = f"{self.gitlab_url}/api/graphql"
        
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                logger.info("Executing GraphQL query")
                async with session.post(url, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if "errors" in result:
                            logger.error(f"GraphQL errors: {result['errors']}")
                        return result.get("data", {})
                    else:
                        logger.error(f"GraphQL query failed: {response.status}")
                        return {}
            except Exception as e:
                logger.error(f"Exception in GraphQL query: {e}")
                return {}
    
    async def get_project_pipelines_graphql(self, project_path: str, last_n: int = 100) -> List[Dict]:
        """Obtiene el historial de pipelines vía GraphQL con datos enriquecidos para análisis."""
        # Consulta GraphQL mejorada para obtener más 'features'
        query = """
        query($projectPath: ID!, $first: Int!) {
          project(fullPath: $projectPath) {
            name
            pipelines(first: $first, orderBy: {field: CREATED_AT, direction: DESC}) {
              nodes {
                id
                iid
                status
                duration
                createdAt
                finishedAt
                source
                user {
                  name
                  username
                }
                jobs(first: 20) {
                  nodes {
                    name
                    status
                    duration
                    failureReason
                  }
                }
              }
            }
          }
        }
        """
        
        variables = {
            "projectPath": project_path,
            "first": last_n
        }
        
        result = await self.graphql_query(query, variables)
        
        if result and "project" in result and result["project"]:
            pipelines = result["project"].get("pipelines", {}).get("nodes", [])
            logger.info(f"Retrieved {len(pipelines)} historical pipelines via GraphQL for project {project_path}")
            return pipelines
        
        return []

    async def get_project_statistics_graphql(self, project_path: str) -> Dict:
        """Get project statistics for prediction model"""
        # Calculate date range for last 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        query = """
        query($projectPath: ID!, $startDate: Time!, $endDate: Time!) {
          project(fullPath: $projectPath) {
            name
            statistics {
              commitCount
              repositorySize
            }
            pipelines(
              first: 500
              ref: "main"
              updatedAfter: $startDate
              updatedBefore: $endDate
            ) {
              count
              nodes {
                id
                status
                duration
                failureReason
                createdAt
                source
              }
            }
          }
        }
        """
        
        variables = {
            "projectPath": project_path,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat()
        }
        
        result = await self.graphql_query(query, variables)
        
        if result and "project" in result and result["project"]:
            project_data = result["project"]
            pipelines = project_data.get("pipelines", {}).get("nodes", [])
            
            # Calculate statistics
            total_pipelines = len(pipelines)
            failed_pipelines = len([p for p in pipelines if p["status"] == "failed"])
            avg_duration = sum(p.get("duration", 0) for p in pipelines) / max(total_pipelines, 1)
            
            # Failure patterns by time of day
            failure_by_hour = {}
            for pipeline in pipelines:
                if pipeline["status"] == "failed" and pipeline.get("createdAt"):
                    hour = datetime.fromisoformat(pipeline["createdAt"].replace("Z", "+00:00")).hour
                    failure_by_hour[hour] = failure_by_hour.get(hour, 0) + 1
            
            return {
                "project_name": project_data.get("name"),
                "total_pipelines_30d": total_pipelines,
                "failed_pipelines_30d": failed_pipelines,
                "failure_rate": failed_pipelines / max(total_pipelines, 1),
                "avg_duration_seconds": avg_duration,
                "failure_by_hour": failure_by_hour,
                "commit_count": project_data.get("statistics", {}).get("commitCount", 0),
                "repository_size": project_data.get("statistics", {}).get("repositorySize", 0)
            }
        
        return {}
    
    async def create_issue(self, project_id: int, title: str, description: str, labels: str = "ai-prediction,pipeline-risk") -> bool:
        """Create an issue for predicted pipeline failure"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/issues"
        
        data = {
            "title": title,
            "description": description,
            "labels": labels
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                logger.info(f"Creating predictive issue: {title}")
                async with session.post(url, headers=self.headers, json=data) as response:
                    success = response.status == 201
                    if success:
                        issue_data = await response.json()
                        logger.info(f"Created issue #{issue_data.get('iid')}")
                        return issue_data
                    else:
                        logger.error(f"Failed to create issue: {response.status}")
                        return None
            except Exception as e:
                logger.error(f"Exception creating issue: {e}")
                return None
        
    async def get_pipeline_jobs(self, project_id: int, pipeline_id: int) -> List[Dict]:
        """Gets all jobs from a pipeline"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs"
        
        async with aiohttp.ClientSession() as session:
            try:
                logger.info(f"Getting jobs for pipeline {pipeline_id}")
                # Try with token if available
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Found {len(result)} jobs")
                        return result
                    else:
                        text = await response.text()
                        logger.error(f"Error getting jobs: {response.status}")
                        logger.error(f"Response: {text}")
                        
                        # If it fails, try without token for public projects
                        if response.status in [401, 403]:
                            logger.info("Retrying without token for public access...")
                            async with session.get(url) as public_response:
                                if public_response.status == 200:
                                    result = await public_response.json()
                                    logger.info(f"Found {len(result)} jobs (public access)")
                                    return result
                                else:
                                    logger.error(f"Failed without token too: {public_response.status}")
                        return []
            except Exception as e:
                logger.error(f"Exception getting jobs: {e}")
                return []
    
    async def get_job_trace(self, project_id: int, job_id: int) -> str:
        """Gets the log of a specific job"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/jobs/{job_id}/trace"
        
        logger.info(f"Getting trace for job {job_id} of project {project_id}")
        
        async with aiohttp.ClientSession() as session:
            try:
                # Try with token first if available
                if self.token:
                    logger.info("Trying with token...")
                    async with session.get(url, headers=self.headers) as response:
                        if response.status == 200:
                            logger.info("Successfully retrieved job trace with token")
                            return await response.text()
                        else:
                            status = response.status
                            text = await response.text()
                            logger.error(f"Error getting job trace with token: {status}")
                            logger.error(f"Response: {text}")
                
                # Try without token for public projects
                logger.info("Trying without token...")
                async with session.get(url) as response:
                    if response.status == 200:
                        logger.info("Successfully retrieved job trace without token")
                        return await response.text()
                    else:
                        status = response.status
                        text = await response.text()
                        logger.error(f"Error getting job trace without token: {status}")
                        logger.error(f"Response: {text}")
                        return ""
                        
            except Exception as e:
                logger.error(f"Exception getting job trace: {e}")
                return ""
    
    async def retry_job(self, project_id: int, job_id: int) -> bool:
        """Retries a failed job"""
        if not self.token:
            logger.warning("No token available for retry operation")
            return False
            
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/jobs/{job_id}/retry"
        
        async with aiohttp.ClientSession() as session:
            try:
                logger.info(f"Attempting to retry job {job_id}")
                async with session.post(url, headers=self.headers) as response:
                    success = response.status == 201
                    if success:
                        logger.info(f"Successfully retried job {job_id}")
                    else:
                        logger.error(f"Failed to retry job {job_id}: {response.status}")
                        text = await response.text()
                        logger.error(f"Response: {text}")
                    return success
            except Exception as e:
                logger.error(f"Exception retrying job: {e}")
                return False
    
    async def create_commit_comment(self, project_id: int, sha: str, body: str) -> bool:
        """Creates a comment on a commit"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/repository/commits/{sha}/comments"
        data = {"note": body}
        
        logger.info(f"Creating commit comment on {sha[:8] if sha else 'None'}")
        
        async with aiohttp.ClientSession() as session:
            try:
                # Try with token if available
                headers = self.headers if self.token else {}
                async with session.post(url, headers=headers, json=data) as response:
                    success = response.status == 201
                    if success:
                        logger.info(f"Successfully created commit comment")
                    else:
                        text = await response.text()
                        logger.error(f"Failed to create commit comment: {response.status}")
                        logger.error(f"Response: {text}")
                    return success
            except Exception as e:
                logger.error(f"Exception creating commit comment: {e}")
                return False
    
    async def create_merge_request_note(self, project_id: int, mr_iid: int, body: str) -> bool:
        """Creates a comment on a merge request"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes"
        
        # In GitLab API, the parameter for comments is 'body'
        data = {"body": body}
        
        logger.info(f"Creating MR note on {mr_iid}")
        
        async with aiohttp.ClientSession() as session:
            try:
                headers = self.headers if self.token else {}
                async with session.post(url, headers=headers, json=data) as response:
                    success = response.status == 201
                    if success:
                        logger.info(f"Successfully created MR note")
                    else:
                        text = await response.text()
                        logger.error(f"Failed to create MR note: {response.status}")
                        logger.error(f"Response: {text}")
                    return success
            except Exception as e:
                logger.error(f"Exception creating MR note: {e}")
                return False
    
    async def get_pipeline_details(self, project_id: int, pipeline_id: int) -> Dict:
        """Gets complete details of a pipeline"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}"
        
        async with aiohttp.ClientSession() as session:
            try:
                logger.info(f"Getting details for pipeline {pipeline_id}")
                # Try with token if available
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        text = await response.text()
                        logger.error(f"Error getting pipeline details: {response.status}")
                        logger.error(f"Response: {text}")
                        
                        # If it fails, try without token for public projects
                        if response.status in [401, 403]:
                            logger.info("Retrying without token for public access...")
                            async with session.get(url) as public_response:
                                if public_response.status == 200:
                                    return await public_response.json()
                        return {}
            except Exception as e:
                logger.error(f"Exception getting pipeline details: {e}")
                return {}
    
    async def get_latest_commit(self, project_id: int, ref: str = "main") -> Dict:
        """Gets the latest commit from a branch"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/repository/commits/{ref}"
        
        async with aiohttp.ClientSession() as session:
            try:
                logger.info(f"Getting latest commit for {ref}")
                # Try with token if available
                async with session.get(url, headers=self.headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        text = await response.text()
                        logger.error(f"Error getting latest commit: {response.status}")
                        logger.error(f"Response: {text}")
                        return {}
            except Exception as e:
                logger.error(f"Exception getting latest commit: {e}")
                return {}