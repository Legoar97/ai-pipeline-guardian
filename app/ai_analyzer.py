import os
from typing import Dict
import logging
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Import Vertex AI correctly
import google.auth
from google.cloud import aiplatform
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

logger = logging.getLogger(__name__)

class AIAnalyzer:
    def __init__(self):
        """Initialize Vertex AI with appropriate credentials"""
        try:
            project_id = os.getenv("GCP_PROJECT_ID", "ai-pipeline-guardian")
            location = os.getenv("GCP_LOCATION", "us-central1")
            
            logger.info(f"Initializing AI Analyzer for project {project_id}")
            
            # Simplified initialization to avoid get_universe_domain error
            vertexai.init(project=project_id, location=location)
            
            # Use Gemini 2.0 Flash
            logger.info("Creating GenerativeModel...")
            self.model = GenerativeModel("gemini-2.0-flash-001")
            
            # Generation configuration
            self.generation_config = GenerationConfig(
                temperature=0.2,
                top_p=0.8,
                top_k=40,
                max_output_tokens=1024,
            )
            
            # Executor for synchronous operations
            self.executor = ThreadPoolExecutor(max_workers=3)
            
            logger.info(f"AI Analyzer initialized with Gemini 2.0 Flash")
            
        except Exception as e:
            logger.error(f"Failed to initialize AI Analyzer: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # Fallback to simple analysis if Vertex AI fails
            self.model = None
    
    def _sync_analyze(self, prompt: str) -> str:
        """Synchronous method to call the model"""
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=self.generation_config
            )
            return response.text
        except Exception as e:
            logger.error(f"Error generating content: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    async def analyze_failure(self, job_log: str, job_name: str = "") -> Dict:
        """Analyze a failure log using Vertex AI"""
        
        # If no model (initialization failed), use simple analysis
        if not self.model:
            logger.warning("Using simple analysis as AI model is not available")
            return self._simple_analysis(job_log, job_name)
        
        # Limit log to last 4000 characters to avoid exceeding limits
        truncated_log = job_log[-4000:] if len(job_log) > 4000 else job_log
        
        prompt = f"""Analyze the following CI/CD log from a job named '{job_name}' that has failed.

Provide your analysis in JSON format with exactly this structure:
{{
    "error_explanation": "brief description of the error (maximum 2 sentences)",
    "error_category": "one of: transient, formatting, failed_test, dependency, configuration, other",
    "recommended_action": "one of: retry, automatic_fix, manual_suggestion",
    "suggested_solution": "specific and actionable solution"
}}

Error categories:
- transient: network errors, timeouts, intermittent failures
- formatting: code style errors, linting
- failed_test: unit or integration tests failing
- dependency: missing packages, incompatible versions (like 'ModuleNotFoundError')
- configuration: missing environment variables, incorrect config files
- other: any other type of error

IMPORTANT: Respond ONLY with the JSON, no additional text or backticks.

Job log:
{truncated_log}
"""
        
        try:
            # Run analysis in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            response_text = await loop.run_in_executor(
                self.executor, 
                self._sync_analyze, 
                prompt
            )
            
            # Try to parse the response as JSON
            try:
                # Clean the response
                cleaned_response = response_text.strip()
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response.split("```")[1]
                    if cleaned_response.startswith("json"):
                        cleaned_response = cleaned_response[4:]
                
                result = json.loads(cleaned_response.strip())
                
                # Validate that it has the required fields
                required_fields = ["error_explanation", "error_category", "recommended_action", "suggested_solution"]
                for field in required_fields:
                    if field not in result:
                        result[field] = "Not available"
                
                logger.info(f"AI Analysis complete: {result['error_category']}")
                return result
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI response as JSON: {e}")
                logger.error(f"Raw response: {response_text}")
                return self._simple_analysis(job_log, job_name)
                
        except Exception as e:
            logger.error(f"Error in AI analysis: {e}")
            logger.error(f"Falling back to simple analysis")
            return self._simple_analysis(job_log, job_name)
    
    def _simple_analysis(self, job_log: str, job_name: str) -> Dict:
        """Simple keyword-based analysis when Vertex AI fails"""
        log_lower = job_log.lower()
        
        if "timeout" in log_lower or "timed out" in log_lower:
            return {
                "error_explanation": "The job failed due to a timeout",
                "error_category": "transient",
                "recommended_action": "retry",
                "suggested_solution": "The job exceeded its time limit. Retry is recommended."
            }
        elif "network" in log_lower or "connection" in log_lower:
            return {
                "error_explanation": "Network connectivity error",
                "error_category": "transient",
                "recommended_action": "retry",
                "suggested_solution": "Network connection failure. Retry is recommended."
            }
        elif "syntaxerror" in log_lower or "unexpected eof" in log_lower:
            return {
                "error_explanation": "Python syntax error in code",
                "error_category": "formatting",
                "recommended_action": "manual_suggestion",
                "suggested_solution": "Review the code syntax. Appears to be missing closing parentheses or quotes."
            }
        elif "modulenotfounderror" in log_lower or "no module named" in log_lower or "import error" in log_lower:
            return {
                "error_explanation": "Missing module or dependency",
                "error_category": "dependency",
                "recommended_action": "manual_suggestion",
                "suggested_solution": "Install the missing dependencies. Add the module to requirements.txt"
            }
        elif "test failed" in log_lower or "assertion" in log_lower or "test error" in log_lower or "exit code 1" in log_lower:
            return {
                "error_explanation": "Test failures detected",
                "error_category": "failed_test",
                "recommended_action": "manual_suggestion",
                "suggested_solution": "Review the failing tests and fix the code"
            }
        else:
            return {
                "error_explanation": "Error not automatically identified",
                "error_category": "other",
                "recommended_action": "manual_suggestion",
                "suggested_solution": "Manually review the logs to identify the issue"
            }