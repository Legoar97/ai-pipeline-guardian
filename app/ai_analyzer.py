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
            self.model = GenerativeModel("gemini-2.0-flash")
            
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
    "error_category": "one of: transient, syntax_error, failed_test, dependency, configuration, timeout, security, other",
    "recommended_action": "one of: retry, automatic_fix, manual_suggestion",
    "suggested_solution": "specific and actionable solution",
    "error_details": {{}}
}}

Error categories:
- transient: network errors, connection issues, intermittent failures
- syntax_error: code syntax errors, indentation errors
- failed_test: unit or integration tests failing
- dependency: missing packages, incompatible versions (like 'ModuleNotFoundError')
- configuration: missing environment variables, incorrect config files
- timeout: job exceeded time limit
- security: vulnerable dependencies, CVEs detected
- other: any other type of error

For automatic_fix, include relevant details in error_details like:
- For syntax_error: error_file, error_line, error_code
- For dependency: missing_module
- For timeout: current_timeout
- For security: vulnerable_package, vulnerable_version
- For configuration: missing_env_var

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
                
                # Ensure error_details exists
                if "error_details" not in result:
                    result["error_details"] = {}
                
                # Extract additional details if not provided by AI
                if not result["error_details"]:
                    result["error_details"] = self._extract_error_details(job_log)
                
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
        
        # Extract specific error details for better fixes
        error_details = self._extract_error_details(job_log)
        
        if "timeout" in log_lower or "timed out" in log_lower:
            return {
                "error_explanation": "The job failed due to a timeout",
                "error_category": "timeout",
                "recommended_action": "automatic_fix",
                "suggested_solution": "Increase the timeout value in .gitlab-ci.yml",
                "error_details": error_details
            }
        elif "network" in log_lower or "connection" in log_lower:
            return {
                "error_explanation": "Network connectivity error",
                "error_category": "transient",
                "recommended_action": "retry",
                "suggested_solution": "Network connection failure. Retry is recommended.",
                "error_details": error_details
            }
        elif "syntaxerror" in log_lower or "unexpected eof" in log_lower or "indentationerror" in log_lower:
            return {
                "error_explanation": "Python syntax error in code",
                "error_category": "syntax_error",
                "recommended_action": "automatic_fix",
                "suggested_solution": "Fix the syntax error in the code",
                "error_details": error_details
            }
        elif "modulenotfounderror" in log_lower or "no module named" in log_lower or "import error" in log_lower:
            return {
                "error_explanation": "Missing module or dependency",
                "error_category": "dependency",
                "recommended_action": "automatic_fix",
                "suggested_solution": "Install the missing dependencies. Add the module to requirements.txt",
                "error_details": error_details
            }
        elif "vulnerabilit" in log_lower or "security" in log_lower or "cve-" in log_lower:
            return {
                "error_explanation": "Security vulnerability detected in dependencies",
                "error_category": "security",
                "recommended_action": "automatic_fix",
                "suggested_solution": "Update vulnerable dependencies to secure versions",
                "error_details": error_details
            }
        elif "keyerror" in log_lower or "environment variable" in log_lower or "config" in log_lower:
            return {
                "error_explanation": "Configuration or environment variable error",
                "error_category": "configuration",
                "recommended_action": "automatic_fix",
                "suggested_solution": "Fix configuration or add missing environment variables",
                "error_details": error_details
            }
        elif "test failed" in log_lower or "assertion" in log_lower or "test error" in log_lower:
            return {
                "error_explanation": "Test failures detected",
                "error_category": "failed_test",
                "recommended_action": "manual_suggestion",
                "suggested_solution": "Review the failing tests and fix the code",
                "error_details": error_details
            }
        else:
            return {
                "error_explanation": "Error not automatically identified",
                "error_category": "other",
                "recommended_action": "manual_suggestion",
                "suggested_solution": "Manually review the logs to identify the issue",
                "error_details": error_details
            }
    
    def _extract_error_details(self, job_log: str) -> Dict:
        """Extract specific error details from the log"""
        details = {}
        
        # Extract Python file and line number for syntax errors
        import re
        syntax_match = re.search(r'File "([^"]+)", line (\d+)', job_log)
        if syntax_match:
            details['error_file'] = syntax_match.group(1)
            details['error_line'] = int(syntax_match.group(2))
            
            # Try to extract the actual error line
            lines = job_log.split('\n')
            for i, line in enumerate(lines):
                if f'line {details["error_line"]}' in line and i + 1 < len(lines):
                    details['error_code'] = lines[i + 1].strip()
                    if i + 2 < len(lines) and '^' in lines[i + 2]:
                        details['error_indicator'] = lines[i + 2]
        
        # Extract module name for import errors
        module_match = re.search(r"No module named '([^']+)'", job_log)
        if module_match:
            details['missing_module'] = module_match.group(1)
        
        # Extract timeout value
        timeout_match = re.search(r'timeout.*?(\d+)', job_log, re.IGNORECASE)
        if timeout_match:
            details['current_timeout'] = int(timeout_match.group(1))
        
        # Extract security vulnerabilities
        cve_matches = re.findall(r'(CVE-\d{4}-\d+)', job_log)
        if cve_matches:
            details['cves'] = cve_matches
        
        # Extract package vulnerabilities
        vuln_match = re.search(r'(\w+)\s*(<|<=|==|>=|>)\s*([\d.]+).*vulnerabilit', job_log, re.IGNORECASE)
        if vuln_match:
            details['vulnerable_package'] = vuln_match.group(1)
            details['vulnerable_version'] = vuln_match.group(3)
        
        # Extract missing environment variables
        env_match = re.search(r"KeyError: '([^']+)'", job_log)
        if not env_match:
            env_match = re.search(r'environment variable.*?([A-Z_]+)', job_log, re.IGNORECASE)
        if env_match:
            details['missing_env_var'] = env_match.group(1)
        
        return details