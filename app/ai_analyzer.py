import vertexai
from vertexai.generative_models import GenerativeModel
import os
import re
import json
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class AIAnalyzer:
    def __init__(self):
        # Initialize Vertex AI
        project_id = os.getenv("GCP_PROJECT_ID", "")
        location = os.getenv("GCP_LOCATION", "us-central1")
        
        if project_id:
            vertexai.init(project=project_id, location=location)
            self.model = GenerativeModel("gemini-2.0-flash-exp")
            logger.info("AI Analyzer initialized with Gemini 2.0 Flash")
        else:
            logger.warning("No GCP project configured, AI analysis disabled")
            self.model = None
    
    def detect_language(self, job_log: str, job_name: str) -> str:
        """Detect programming language from log patterns and job name"""
        # Language indicators
        language_patterns = {
            'python': [
                r'\.py\b', r'python', r'pip install', r'requirements\.txt',
                r'ModuleNotFoundError', r'SyntaxError.*line \d+', r'IndentationError',
                r'pytest', r'unittest', r'django', r'flask'
            ],
            'javascript': [
                r'\.js\b', r'node', r'npm', r'package\.json', r'yarn',
                r'SyntaxError.*Unexpected token', r'ReferenceError', r'TypeError.*undefined',
                r'jest', r'mocha', r'webpack', r'babel'
            ],
            'java': [
                r'\.java\b', r'javac', r'maven', r'gradle', r'pom\.xml',
                r'Exception in thread', r'ClassNotFoundException', r'NullPointerException',
                r'junit', r'spring'
            ],
            'go': [
                r'\.go\b', r'go build', r'go test', r'go\.mod', r'go get',
                r'panic:', r'undefined:', r'cannot find package'
            ],
            'ruby': [
                r'\.rb\b', r'ruby', r'gem install', r'Gemfile', r'bundle',
                r'NoMethodError', r'NameError', r'SyntaxError.*unexpected',
                r'rspec', r'rails'
            ],
            'php': [
                r'\.php\b', r'composer', r'composer\.json', r'phpunit',
                r'Fatal error:', r'Parse error:', r'Uncaught Error:'
            ],
            'rust': [
                r'\.rs\b', r'cargo', r'Cargo\.toml', r'rustc',
                r'error\[E\d+\]', r'cannot find', r'unresolved import'
            ],
            'csharp': [
                r'\.cs\b', r'dotnet', r'\.csproj', r'nuget',
                r'CS\d{4}:', r'System\..*Exception', r'NullReferenceException'
            ],
            'typescript': [
                r'\.ts\b', r'tsc', r'tsconfig\.json', r'typescript',
                r'TS\d+:', r'Type.*is not assignable'
            ]
        }
        
        # Check each language
        scores = {}
        combined_text = f"{job_name} {job_log}".lower()
        
        for lang, patterns in language_patterns.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, combined_text, re.IGNORECASE):
                    score += 1
            scores[lang] = score
        
        # Return language with highest score, default to python
        detected = max(scores.items(), key=lambda x: x[1])
        return detected[0] if detected[1] > 0 else 'python'
    
    async def analyze_failure(self, job_log: str, job_name: str = "") -> Dict:
        """Analyze CI/CD failure using Vertex AI with multi-language support"""
        
        if not self.model:
            return self._get_fallback_analysis(job_log)
        
        # Detect language
        language = self.detect_language(job_log, job_name)
        logger.info(f"Detected language: {language}")
        
        # Clean the log
        cleaned_log = self._clean_log(job_log)
        
        prompt = f"""You are an expert DevOps engineer analyzing a CI/CD pipeline failure.

DETECTED LANGUAGE: {language}

Analyze this job log and provide a structured response:

JOB NAME: {job_name}
LOG OUTPUT:
{cleaned_log}

Provide your analysis in this EXACT JSON format:
{{
    "error_category": "dependency|syntax_error|test_failure|timeout|network|security|configuration|build_error|other",
    "error_explanation": "Clear explanation of what went wrong",
    "suggested_solution": "Specific steps to fix the issue",
    "recommended_action": "retry|manual_fix|automatic_fix",
    "confidence": 0.0-1.0,
    "language": "{language}",
    "error_details": {{
        "error_file": "filename if applicable",
        "error_line": line_number_if_applicable,
        "error_code": "the actual line of code that failed if visible",
        "missing_module": "module name if dependency error",
        "test_name": "test name if test failure",
        "timeout_value": seconds_if_timeout,
        "vulnerable_package": "package if security issue",
        "vulnerable_version": "version if security issue",
        "cves": ["CVE-XXXX-XXXX"],
        "missing_env_var": "VAR_NAME if configuration error",
        "language_specific": {{
            // Additional details specific to the detected language
        }}
    }}
}}

IMPORTANT RULES FOR {language.upper()}:
- For dependency errors: Identify the exact package/module name
- For syntax errors: Locate the specific file and line number
- For test failures: Extract the test name and assertion
- Consider language-specific package managers and error patterns
- Set recommended_action to "automatic_fix" ONLY for errors we can fix programmatically

Focus on the most critical error if there are multiple issues."""

        try:
            response = self.model.generate_content(prompt)
            result_text = response.text.strip()
            
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                
                # Add language detection
                result['language'] = language
                
                # Ensure all required fields
                required_fields = {
                    'error_category': 'other',
                    'error_explanation': 'Error analysis failed',
                    'suggested_solution': 'Manual review required',
                    'recommended_action': 'manual_fix',
                    'confidence': 0.5,
                    'language': language,
                    'error_details': {}
                }
                
                for field, default in required_fields.items():
                    if field not in result:
                        result[field] = default
                
                # Language-specific enhancements
                result = self._enhance_language_specific(result, language, job_log)
                
                logger.info(f"AI Analysis complete: {result['error_category']} ({language})")
                return result
            else:
                logger.error("No JSON found in AI response")
                return self._get_fallback_analysis(job_log)
                
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            return self._get_fallback_analysis(job_log)
    
    def _enhance_language_specific(self, result: Dict, language: str, job_log: str) -> Dict:
        """Add language-specific enhancements to the analysis"""
        
        error_details = result.get('error_details', {})
        
        if language == 'javascript' and result['error_category'] == 'dependency':
            # Check for npm vs yarn
            if 'yarn' in job_log.lower():
                error_details['package_manager'] = 'yarn'
                error_details['install_command'] = 'yarn add'
            else:
                error_details['package_manager'] = 'npm'
                error_details['install_command'] = 'npm install'
        
        elif language == 'java' and result['error_category'] == 'dependency':
            # Check for Maven vs Gradle
            if 'pom.xml' in job_log or 'mvn' in job_log:
                error_details['build_tool'] = 'maven'
                error_details['config_file'] = 'pom.xml'
            else:
                error_details['build_tool'] = 'gradle'
                error_details['config_file'] = 'build.gradle'
        
        elif language == 'go' and result['error_category'] == 'dependency':
            # Extract Go module path
            match = re.search(r'cannot find package "([^"]+)"', job_log)
            if match:
                error_details['go_module'] = match.group(1)
        
        elif language == 'ruby' and result['error_category'] == 'dependency':
            # Extract gem name
            match = re.search(r"Could not find '([^']+)'", job_log)
            if match:
                error_details['gem_name'] = match.group(1)
        
        result['error_details'] = error_details
        return result
    
    def _clean_log(self, log: str, max_lines: int = 200) -> str:
        """Clean and truncate log for AI analysis"""
        lines = log.split('\n')
        
        # Find the most relevant part (usually the end)
        if len(lines) > max_lines:
            # Look for error indicators
            error_keywords = [
                'error', 'failed', 'exception', 'traceback', 'fatal',
                'panic', 'undefined', 'cannot find', 'missing', 'not found'
            ]
            
            # Find last occurrence of error keywords
            last_error_index = -1
            for i, line in enumerate(lines):
                if any(keyword in line.lower() for keyword in error_keywords):
                    last_error_index = i
            
            # Include context around the error
            if last_error_index >= 0:
                start = max(0, last_error_index - 50)
                end = min(len(lines), last_error_index + 100)
                lines = lines[start:end]
            else:
                # Just take the last max_lines
                lines = lines[-max_lines:]
        
        # Remove ANSI codes and excessive whitespace
        cleaned_lines = []
        for line in lines:
            # Remove ANSI escape codes
            line = re.sub(r'\x1b\[[0-9;]*m', '', line)
            # Remove GitLab CI specific prefixes with timestamps
            line = re.sub(r'^\[\d+:\d+:\d+\]\s*', '', line)
            # Skip empty lines
            if line.strip():
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _get_fallback_analysis(self, job_log: str) -> Dict:
        """Fallback analysis when AI is not available"""
        # Detect language even in fallback
        language = self.detect_language(job_log, "")
        
        # Basic pattern matching
        if "ModuleNotFoundError" in job_log or "ImportError" in job_log:
            match = re.search(r"No module named '([^']+)'", job_log)
            module = match.group(1) if match else "unknown"
            return {
                "error_category": "dependency",
                "error_explanation": f"Missing Python module: {module}",
                "suggested_solution": f"Add {module} to requirements.txt",
                "recommended_action": "automatic_fix",
                "confidence": 0.8,
                "language": "python",
                "error_details": {"missing_module": module}
            }
        elif "npm ERR!" in job_log or "Cannot find module" in job_log:
            match = re.search(r"Cannot find module '([^']+)'", job_log)
            module = match.group(1) if match else "unknown"
            return {
                "error_category": "dependency",
                "error_explanation": f"Missing Node.js module: {module}",
                "suggested_solution": f"Run npm install {module}",
                "recommended_action": "automatic_fix",
                "confidence": 0.8,
                "language": "javascript",
                "error_details": {"missing_module": module}
            }
        elif "timeout" in job_log.lower() or "timed out" in job_log.lower():
            return {
                "error_category": "timeout",
                "error_explanation": "Job exceeded time limit",
                "suggested_solution": "Increase job timeout in .gitlab-ci.yml",
                "recommended_action": "automatic_fix",
                "confidence": 0.7,
                "language": language,
                "error_details": {"current_timeout": 3600}
            }
        else:
            return {
                "error_category": "other",
                "error_explanation": "Build failed - manual review required",
                "suggested_solution": "Check the full job log for details",
                "recommended_action": "manual_fix",
                "confidence": 0.3,
                "language": language,
                "error_details": {}
            }