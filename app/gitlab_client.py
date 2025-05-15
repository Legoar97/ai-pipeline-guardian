import os
import aiohttp
from typing import Dict, List, Optional
import logging

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