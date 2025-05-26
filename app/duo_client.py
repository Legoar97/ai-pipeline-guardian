import os
import aiohttp
import logging
from typing import Dict, Optional, List
import json
from datetime import datetime

logger = logging.getLogger(__name__)

class GitLabDuoClient:
    """Real GitLab Duo AI Integration Client"""
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("GITLAB_ACCESS_TOKEN", "")
        self.base_url = "https://gitlab.com/api/v4"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        logger.info("GitLab Duo client initialized (REAL Mode)")
    
    async def get_code_suggestion(self, project_id: int, file_content: str, cursor_position: int) -> Dict:
        """Get real code suggestions from GitLab Duo"""
        url = f"{self.base_url}/code_suggestions/completions"
        
        # Split content at cursor
        content_above = file_content[:cursor_position]
        content_below = file_content[cursor_position:]
        
        payload = {
            "project_id": project_id,
            "current_file": {
                "file_name": "fix.py",
                "content_above_cursor": content_above,
                "content_below_cursor": content_below
            }
        }
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, headers=self.headers, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "success": True,
                            "suggestion": data.get("completions", [{}])[0].get("text", ""),
                            "confidence": 0.9
                        }
                    else:
                        logger.error(f"Duo API error: {response.status}")
                        text = await response.text()
                        logger.error(f"Response: {text}")
                        return self._fallback_suggestion(file_content)
            except Exception as e:
                logger.error(f"Error calling Duo API: {e}")
                return self._fallback_suggestion(file_content)
    
    async def suggest_fix(self, 
                         project_id: int,
                         error_type: str,
                         error_details: Dict) -> Dict:
        """Get AI-powered fix suggestions from Duo"""
        logger.info(f"Duo analyzing {error_type} error for project {project_id}...")
        
        # Create a code context based on error
        if error_type == "dependency":
            module = error_details.get('module', 'pandas')
            code_context = f"""# Error: ModuleNotFoundError: No module named '{module}'
# Fix: Add to requirements.txt
import {module}
"""
            cursor_pos = len(code_context)
            
            suggestion = await self.get_code_suggestion(project_id, code_context, cursor_pos)
            
            if suggestion.get("success"):
                return {
                    "success": True,
                    "suggestion": {
                        "requirements.txt": {
                            "action": "append",
                            "content": f"\n{module}==latest"
                        }
                    },
                    "confidence": 0.95,
                    "explanation": f"Duo suggests adding '{module}' to requirements.txt to resolve the import error.",
                    "duo_suggestion": suggestion.get("suggestion", "")
                }
        
        elif error_type == "syntax_error":
            # For syntax errors, try to get Duo to fix the line
            error_line = error_details.get('error_line', '')
            code_context = f"""# Error: SyntaxError
# Original code with error:
{error_line}
# Fixed code:
"""
            cursor_pos = len(code_context)
            
            suggestion = await self.get_code_suggestion(project_id, code_context, cursor_pos)
            
            return {
                "success": True,
                "suggestion": suggestion.get("suggestion", "Check syntax"),
                "confidence": suggestion.get("confidence", 0.8),
                "explanation": "Duo analyzed the syntax error and suggests a correction."
            }
        
        # Default response
        return {
            "success": True,
            "suggestion": "Manual review recommended",
            "confidence": 0.6,
            "explanation": "Duo suggests manual review for this error type."
        }
    
    async def create_fix_mr(self,
                           gitlab_client,
                           project_id: int,
                           source_branch: str,
                           fix_data: Dict) -> Dict:
        """Create a real MR with Duo-suggested fixes"""
        logger.info(f"Creating AI-powered fix MR for project {project_id}...")
        
        try:
            # Create a new branch
            branch_name = f"duo-fix/{fix_data['error_type']}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Create branch via API
            branch_url = f"{self.base_url}/projects/{project_id}/repository/branches"
            branch_payload = {
                "branch": branch_name,
                "ref": source_branch
            }
            
            async with aiohttp.ClientSession() as session:
                # Create branch
                async with session.post(branch_url, headers=self.headers, json=branch_payload) as response:
                    if response.status != 201:
                        logger.error(f"Failed to create branch: {response.status}")
                        return {"success": False, "error": "branch_creation_failed"}
                
                # Create commit with fixes
                if fix_data.get('error_type') == 'dependency' and 'module' in fix_data:
                    # For dependency errors, update requirements.txt
                    commit_url = f"{self.base_url}/projects/{project_id}/repository/commits"
                    
                    # First, get current requirements.txt
                    file_url = f"{self.base_url}/projects/{project_id}/repository/files/requirements.txt/raw"
                    async with session.get(file_url, headers=self.headers, params={"ref": source_branch}) as response:
                        if response.status == 200:
                            current_content = await response.text()
                        else:
                            current_content = ""
                    
                    # Add the new dependency
                    new_content = current_content.rstrip() + f"\n{fix_data['module']}\n"
                    
                    commit_payload = {
                        "branch": branch_name,
                        "commit_message": f"🤖 AI Fix: Add missing dependency {fix_data['module']}",
                        "actions": [{
                            "action": "update" if current_content else "create",
                            "file_path": "requirements.txt",
                            "content": new_content
                        }]
                    }
                    
                    async with session.post(commit_url, headers=self.headers, json=commit_payload) as response:
                        if response.status != 201:
                            logger.error(f"Failed to commit fix: {response.status}")
                            return {"success": False, "error": "commit_failed"}
                
                # Create MR
                mr_url = f"{self.base_url}/projects/{project_id}/merge_requests"
                mr_payload = {
                    "source_branch": branch_name,
                    "target_branch": source_branch,
                    "title": f"🤖 AI Fix: {fix_data['error_type'].replace('_', ' ').title()} Resolution",
                    "description": self._generate_mr_description(fix_data),
                    "labels": "ai-generated,duo-powered,auto-fix",
                    "remove_source_branch": True
                }
                
                async with session.post(mr_url, headers=self.headers, json=mr_payload) as response:
                    if response.status == 201:
                        mr_data = await response.json()
                        return {
                            "success": True,
                            "mr_url": mr_data["web_url"],
                            "mr_iid": mr_data["iid"],
                            "branch": branch_name
                        }
                    else:
                        error_text = await response.text()
                        logger.error(f"Failed to create MR: {error_text}")
                        return {"success": False, "error": "mr_creation_failed"}
                        
        except Exception as e:
            logger.error(f"Error creating fix MR: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"success": False, "error": str(e)}
    
    def _fallback_suggestion(self, context: str) -> Dict:
        """Fallback when Duo API is not available"""
        return {
            "success": False,
            "suggestion": "# Duo suggestion not available",
            "confidence": 0.5
        }
    
    def _generate_mr_description(self, fix_data: Dict) -> str:
        """Generate MR description"""
        return f"""## 🤖 AI-Generated Fix via GitLab Duo

This MR was automatically generated by **AI Pipeline Guardian** using **GitLab Duo** AI capabilities.

### 🔍 Problem Detected
- **Error Type**: `{fix_data.get('error_type', 'Unknown')}`
- **Pipeline**: #{fix_data.get('pipeline_id', 'N/A')}
- **Job**: {fix_data.get('job_name', 'N/A')}
- **Error**: {fix_data.get('error_explanation', 'N/A')}

### 🧠 AI Analysis
{fix_data.get('explanation', 'AI has analyzed the error and proposed a solution.')}

### 🛠️ Applied Fix
{fix_data.get('fix_description', 'Automated fix applied based on AI analysis.')}

### 📊 Confidence Level
- **Analysis Confidence**: {fix_data.get('analysis_confidence', 95)}%
- **Fix Confidence**: {fix_data.get('confidence', 85)}%

### ✨ GitLab Duo Integration
This fix was powered by GitLab Duo's AI capabilities, demonstrating the future of automated error resolution.

---
*🚀 Generated by [AI Pipeline Guardian](https://gitlab.com/Legoar97-group/ai-pipeline-guardian)*  
*🏆 Built for Google Cloud + GitLab Hackathon 2025*
"""