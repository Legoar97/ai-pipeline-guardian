import os
from typing import Dict
import logging
import json
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Importar correctamente Vertex AI
import google.auth
from google.cloud import aiplatform
import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

logger = logging.getLogger(__name__)

class AIAnalyzer:
    def __init__(self):
        """Inicializar Vertex AI con las credenciales apropiadas"""
        try:
            project_id = os.getenv("GCP_PROJECT_ID", "ai-pipeline-guardian")
            location = os.getenv("GCP_LOCATION", "us-central1")
            
            # Obtener credenciales
            credentials, _ = google.auth.default()
            
            # Inicializar Vertex AI con credenciales
            vertexai.init(
                project=project_id, 
                location=location,
                credentials=credentials
            )
            
            # Usar Gemini Pro
            self.model = GenerativeModel("gemini-pro")
            
            # Configuración de generación
            self.generation_config = GenerationConfig(
                temperature=0.2,
                top_p=0.8,
                top_k=40,
                max_output_tokens=1024,
            )
            
            # Executor para operaciones síncronas
            self.executor = ThreadPoolExecutor(max_workers=3)
            
            logger.info(f"AI Analyzer initialized with Gemini Pro for project {project_id}")
            
        except Exception as e:
            logger.error(f"Failed to initialize AI Analyzer: {e}")
            # Fallback a análisis simple si falla Vertex AI
            self.model = None
    
    def _sync_analyze(self, prompt: str) -> str:
        """Método síncrono para llamar al modelo"""
        try:
            response = self.model.generate_content(
                prompt,
                generation_config=self.generation_config
            )
            return response.text
        except Exception as e:
            logger.error(f"Error generating content: {e}")
            raise
    
    async def analyze_failure(self, job_log: str, job_name: str = "") -> Dict:
        """Analiza un log de fallo usando Vertex AI"""
        
        # Si no hay modelo (falló la inicialización), usar análisis simple
        if not self.model:
            logger.warning("Using simple analysis as AI model is not available")
            return self._simple_analysis(job_log, job_name)
        
        # Limitar el log a los últimos 4000 caracteres para no exceder límites
        truncated_log = job_log[-4000:] if len(job_log) > 4000 else job_log
        
        prompt = f"""Analiza el siguiente log de CI/CD de un job llamado '{job_name}' que ha fallado.

Proporciona tu análisis en formato JSON con exactamente esta estructura:
{{
    "error_explanation": "descripción breve del error (máximo 2 frases)",
    "error_category": "una de: transitorio, formato, test_fallido, dependencia, configuracion, otro",
    "recommended_action": "una de: reintentar, fix_automatico, sugerencia_manual",
    "suggested_solution": "solución específica y accionable"
}}

Categorías de error:
- transitorio: errores de red, timeouts, fallos intermitentes
- formato: errores de estilo de código, linting
- test_fallido: tests unitarios o de integración fallidos
- dependencia: paquetes faltantes, versiones incompatibles (como 'ModuleNotFoundError')
- configuracion: variables de entorno faltantes, archivos de config incorrectos
- otro: cualquier otro tipo de error

IMPORTANTE: Responde SOLO con el JSON, sin texto adicional ni backticks.

Log del job:
{truncated_log}
"""
        
        try:
            # Ejecutar análisis en thread pool para no bloquear
            loop = asyncio.get_event_loop()
            response_text = await loop.run_in_executor(
                self.executor, 
                self._sync_analyze, 
                prompt
            )
            
            # Intentar parsear la respuesta como JSON
            try:
                # Limpiar la respuesta
                cleaned_response = response_text.strip()
                if cleaned_response.startswith("```"):
                    cleaned_response = cleaned_response.split("```")[1]
                    if cleaned_response.startswith("json"):
                        cleaned_response = cleaned_response[4:]
                
                result = json.loads(cleaned_response.strip())
                
                # Validar que tiene los campos requeridos
                required_fields = ["error_explanation", "error_category", "recommended_action", "suggested_solution"]
                for field in required_fields:
                    if field not in result:
                        result[field] = "No disponible"
                
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
        """Análisis simple basado en palabras clave cuando falla Vertex AI"""
        log_lower = job_log.lower()
        
        if "timeout" in log_lower or "timed out" in log_lower:
            return {
                "error_explanation": "El job falló por timeout",
                "error_category": "transitorio",
                "recommended_action": "reintentar",
                "suggested_solution": "El job excedió el tiempo límite. Se recomienda reintentar."
            }
        elif "network" in log_lower or "connection" in log_lower:
            return {
                "error_explanation": "Error de conectividad de red",
                "error_category": "transitorio",
                "recommended_action": "reintentar",
                "suggested_solution": "Fallo de conexión de red. Se recomienda reintentar."
            }
        elif "syntaxerror" in log_lower or "unexpected eof" in log_lower:
            return {
                "error_explanation": "Error de sintaxis en el código Python",
                "error_category": "formato",
                "recommended_action": "sugerencia_manual",
                "suggested_solution": "Revisar la sintaxis del código. Parece faltar cerrar paréntesis o comillas."
            }
        elif "modulenotfounderror" in log_lower or "no module named" in log_lower or "import error" in log_lower:
            return {
                "error_explanation": "Módulo o dependencia faltante",
                "error_category": "dependencia",
                "recommended_action": "sugerencia_manual",
                "suggested_solution": "Instalar las dependencias faltantes. Agregar el módulo a requirements.txt"
            }
        elif "test failed" in log_lower or "assertion" in log_lower or "test error" in log_lower:
            return {
                "error_explanation": "Fallo en las pruebas",
                "error_category": "test_fallido",
                "recommended_action": "sugerencia_manual",
                "suggested_solution": "Revisar las pruebas fallidas y corregir el código"
            }
        else:
            return {
                "error_explanation": "Error no identificado automáticamente",
                "error_category": "otro",
                "recommended_action": "sugerencia_manual",
                "suggested_solution": "Revisar los logs manualmente para identificar el problema"
            }