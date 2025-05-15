import os
import aiohttp
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class GitLabClient:
    def __init__(self, gitlab_url: str = "https://gitlab.com", token: Optional[str] = None):
        self.gitlab_url = gitlab_url
        self.token = token or os.getenv("GITLAB_ACCESS_TOKEN", "")
        self.headers = {"PRIVATE-TOKEN": self.token} if self.token else {}
        logger.info(f"GitLab client initialized. Token present: {'Yes' if self.token else 'No'}")
        
    async def get_pipeline_jobs(self, project_id: int, pipeline_id: int) -> List[Dict]:
        """Obtiene todos los jobs de un pipeline"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs"
        
        async with aiohttp.ClientSession() as session:
            try:
                # Intentar primero con token si está disponible
                headers = self.headers if self.token else {}
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        text = await response.text()
                        logger.error(f"Error getting jobs: {response.status}")
                        logger.error(f"Response: {text}")
                        
                        # Si falla con token, intentar sin token (público)
                        if response.status in [401, 403] and self.token:
                            logger.info("Retrying without token for public access...")
                            async with session.get(url) as public_response:
                                if public_response.status == 200:
                                    return await public_response.json()
                        return []
            except Exception as e:
                logger.error(f"Exception getting jobs: {e}")
                return []
    
    async def get_job_trace(self, project_id: int, job_id: int) -> str:
        """Obtiene el log de un job específico"""
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/jobs/{job_id}/trace"
        
        async with aiohttp.ClientSession() as session:
            try:
                # Si el proyecto es público, intentar sin token primero
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.text()
                    
                    # Si falla, intentar con token
                    if self.token and response.status in [401, 403]:
                        logger.info("Retrying with token...")
                        async with session.get(url, headers=self.headers) as auth_response:
                            if auth_response.status == 200:
                                return await auth_response.text()
                            else:
                                logger.error(f"Error getting job trace with token: {auth_response.status}")
                                return ""
                    else:
                        logger.error(f"Error getting job trace: {response.status}")
                        return ""
            except Exception as e:
                logger.error(f"Exception getting job trace: {e}")
                return ""
    
    async def retry_job(self, project_id: int, job_id: int) -> bool:
        """Reintenta un job fallido"""
        if not self.token:
            logger.warning("No token available for retry operation")
            return False
            
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/jobs/{job_id}/retry"
        
        async with aiohttp.ClientSession() as session:
            try:
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
        """Crea un comentario en un commit - simplificado para proyectos públicos"""
        # Para proyectos públicos, podemos usar la API sin autenticación
        url = f"{self.gitlab_url}/api/v4/projects/{project_id}/repository/commits/{sha}/comments"
        data = {"note": body}
        
        async with aiohttp.ClientSession() as session:
            try:
                # Primero intentar sin token (si el proyecto es público)
                async with session.post(url, json=data) as response:
                    if response.status == 201:
                        return True
                    
                    # Si falla, intentar con token
                    if self.token and response.status in [401, 403]:
                        async with session.post(url, headers=self.headers, json=data) as auth_response:
                            success = auth_response.status == 201
                            if not success:
                                text = await auth_response.text()
                                logger.error(f"Failed to create commit comment with token: {text}")
                            return success
                    else:
                        text = await response.text()
                        logger.error(f"Failed to create commit comment: {text}")
                        return False
            except Exception as e:
                logger.error(f"Exception creating commit comment: {e}")
                return False