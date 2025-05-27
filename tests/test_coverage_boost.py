# tests/test_coverage_boost.py
"""Additional tests to boost code coverage to 70%+"""

import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
import json
from fastapi.testclient import TestClient
from app.main import app, processed_pipelines, created_mrs, pipeline_analytics
from app.ai_analyzer import AIAnalyzer
from app.vertex_ai_fixer import VertexAIFixer
from app.gitlab_client import GitLabClient
from app.firestore_client import FirestoreClient

client = TestClient(app)

class TestMainAdditional:
    """Additional tests for main.py coverage"""
    
    def test_dashboard_endpoint(self):
        """Test dashboard endpoint"""
        with patch('app.main.firestore_client.get_dashboard_stats') as mock_stats:
            mock_stats.return_value = {
                'total_pipelines': 10,
                'time_saved_hours': 5.5,
                'total_mrs_created': 3,
                'total_retries': 7,
                'success_rate': 85.0,
                'recent_analyses': [],
                'daily_stats': [],
                'error_categories': {},
                'error_patterns': []
            }
            
            response = client.get("/dashboard")
            assert response.status_code == 200
            assert "AI Pipeline Guardian" in response.text
            assert "Analytics" in response.text
    
    def test_dashboard_endpoint_error(self):
        """Test dashboard endpoint error handling"""
        with patch('app.main.firestore_client.get_dashboard_stats') as mock_stats:
            mock_stats.side_effect = Exception("Database error")
            
            response = client.get("/dashboard")
            assert response.status_code == 500
    
    def test_manual_analyze_endpoint(self):
        """Test manual analysis endpoint"""
        request_data = {
            "pipeline": {"id": 12345},
            "project": {"id": 67890, "name": "test-project"}
        }
        
        # Mock the webhook processing
        with patch('app.main.processed_pipelines'):
            response = client.post("/analyze", json=request_data)
            assert response.status_code == 200
    
    def test_manual_analyze_missing_data(self):
        """Test manual analysis with missing data"""
        request_data = {
            "pipeline": {},
            "project": {}
        }
        
        response = client.post("/analyze", json=request_data)
        assert response.status_code == 400
    
    def test_pipeline_start_endpoint(self):
        """Test pipeline start tracking endpoint"""
        response = client.post("/pipeline/start", json={"pipeline_id": 12345})
        assert response.status_code == 200
        assert response.json()["status"] == "acknowledged"
    
    def test_webhook_non_pipeline_event(self):
        """Test webhook with non-pipeline event"""
        response = client.post(
            "/webhook",
            json={"event": "push"},
            headers={"X-Gitlab-Event": "Push Hook"}
        )
        assert response.status_code == 200
        assert response.json()["event"] == "Push Hook"
    
    def test_webhook_duplicate_processing_prevention(self):
        """Test that duplicate pipelines are not processed"""
        # Mark pipeline as recently processed
        pipeline_id = 99999
        processed_pipelines[pipeline_id] = datetime.now() - timedelta(minutes=5)
        
        webhook_payload = {
            "object_attributes": {
                "id": pipeline_id,
                "status": "failed",
                "ref": "main"
            },
            "project": {
                "id": 67890,
                "name": "test-project"
            }
        }
        
        response = client.post(
            "/webhook",
            json=webhook_payload,
            headers={"X-Gitlab-Event": "Pipeline Hook"}
        )
        
        assert response.status_code == 200
        assert response.json()["status"] == "skipped"
        assert response.json()["reason"] == "recently_processed"
    
    @patch('app.main.gitlab_client.get_pipeline_jobs')
    @patch('app.main.gitlab_client.get_job_trace')
    @patch('app.main.ai_analyzer.analyze_failure')
    @patch('app.main.gitlab_client.retry_job')
    def test_webhook_retry_transient_error(
        self, mock_retry, mock_analyze, mock_trace, mock_jobs
    ):
        """Test webhook retries transient errors"""
        # Setup mocks
        mock_jobs.return_value = [{
            "id": 111,
            "name": "test-job",
            "status": "failed"
        }]
        mock_trace.return_value = "Connection timeout"
        mock_analyze.return_value = {
            "error_category": "transient",
            "error_explanation": "Network timeout",
            "suggested_solution": "Retry the job",
            "recommended_action": "retry",
            "language": "python",
            "error_details": {}
        }
        mock_retry.return_value = True
        
        webhook_payload = {
            "object_attributes": {
                "id": 88888,
                "status": "failed",
                "ref": "main"
            },
            "project": {
                "id": 67890,
                "name": "test-project"
            }
        }
        
        with patch('app.main.GITLAB_ACCESS_TOKEN', 'test-token'):
            response = client.post(
                "/webhook",
                json=webhook_payload,
                headers={"X-Gitlab-Event": "Pipeline Hook"}
            )
        
        assert response.status_code == 200
        # Should have called retry
        mock_retry.assert_called_once()

class TestAIAnalyzerAdditional:
    """Additional tests for AI Analyzer coverage"""
    
    @pytest.fixture
    def analyzer(self):
        with patch('app.ai_analyzer.vertexai.init'):
            with patch('app.ai_analyzer.GenerativeModel'):
                return AIAnalyzer()
    
    @pytest.mark.asyncio
    async def test_analyze_failure_with_model(self, analyzer):
        """Test analyze failure when model is available"""
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text = json.dumps({
            "error_category": "dependency",
            "error_explanation": "Missing module",
            "suggested_solution": "Install module",
            "recommended_action": "automatic_fix",
            "confidence": 0.9,
            "language": "python",
            "error_details": {"missing_module": "test-module"}
        })
        mock_model.generate_content.return_value = mock_response
        analyzer.model = mock_model
        
        result = await analyzer.analyze_failure("ModuleNotFoundError: test", "job")
        assert result["error_category"] == "dependency"
        assert result["confidence"] == 0.9
    
    @pytest.mark.asyncio
    async def test_analyze_failure_json_error(self, analyzer):
        """Test analyze failure with invalid JSON response"""
        mock_model = Mock()
        mock_response = Mock()
        mock_response.text = "Invalid JSON response"
        mock_model.generate_content.return_value = mock_response
        analyzer.model = mock_model
        
        result = await analyzer.analyze_failure("Some error", "job")
        # Should fall back to simple analysis
        assert result["error_category"] == "other"
    
    def test_enhance_language_specific_javascript(self, analyzer):
        """Test JavaScript-specific enhancements"""
        result = {
            "error_category": "dependency",
            "error_details": {}
        }
        job_log = "yarn add express"
        
        enhanced = analyzer._enhance_language_specific(result, "javascript", job_log)
        assert enhanced["error_details"]["package_manager"] == "yarn"
        assert enhanced["error_details"]["install_command"] == "yarn add"
    
    def test_enhance_language_specific_java(self, analyzer):
        """Test Java-specific enhancements"""
        result = {
            "error_category": "dependency",
            "error_details": {}
        }
        job_log = "mvn clean install"
        
        enhanced = analyzer._enhance_language_specific(result, "java", job_log)
        assert enhanced["error_details"]["build_tool"] == "maven"
        assert enhanced["error_details"]["config_file"] == "pom.xml"
    
    def test_enhance_language_specific_go(self, analyzer):
        """Test Go-specific enhancements"""
        result = {
            "error_category": "dependency",
            "error_details": {}
        }
        job_log = 'cannot find package "github.com/test/pkg"'
        
        enhanced = analyzer._enhance_language_specific(result, "go", job_log)
        assert enhanced["error_details"]["go_module"] == "github.com/test/pkg"
    
    def test_enhance_language_specific_ruby(self, analyzer):
        """Test Ruby-specific enhancements"""
        result = {
            "error_category": "dependency",
            "error_details": {}
        }
        job_log = "Could not find 'rails'"
        
        enhanced = analyzer._enhance_language_specific(result, "ruby", job_log)
        assert enhanced["error_details"]["gem_name"] == "rails"
    
    def test_get_fallback_analysis_timeout(self, analyzer):
        """Test fallback analysis for timeout errors"""
        job_log = "Job timed out after 3600 seconds"
        result = analyzer._get_fallback_analysis(job_log)
        assert result["error_category"] == "timeout"
        assert result["recommended_action"] == "automatic_fix"
    
    def test_get_fallback_analysis_javascript(self, analyzer):
        """Test fallback analysis for JavaScript errors"""
        job_log = "npm ERR! Cannot find module 'express'"
        result = analyzer._get_fallback_analysis(job_log)
        assert result["error_category"] == "dependency"
        assert result["language"] == "javascript"
        assert result["error_details"]["missing_module"] == "express"

class TestVertexAIFixerAdditional:
    """Additional tests for Vertex AI Fixer coverage"""
    
    @pytest.fixture
    def fixer(self):
        return VertexAIFixer(token="test-token")
    
    @pytest.mark.asyncio
    async def test_fix_syntax_error(self, fixer):
        """Test syntax error fix generation"""
        result = await fixer._fix_syntax_error(
            {"error_file": "test.py", "error_line": 10, "error_code": "if True"},
            "SyntaxError: invalid syntax"
        )
        
        assert result["success"] is True
        assert result["fix_type"] == "syntax_error"
        assert "Add missing colon" in result["suggestion"]["fix"]
    
    @pytest.mark.asyncio
    async def test_fix_syntax_error_quotes(self, fixer):
        """Test syntax error fix for unclosed quotes"""
        result = await fixer._fix_syntax_error(
            {"error_file": "test.py", "error_line": 10, "error_code": 'print("test)'},
            "SyntaxError: unterminated string"
        )
        
        assert result["success"] is True
        assert "unclosed string quote" in result["suggestion"]["fix"]
    
    @pytest.mark.asyncio
    async def test_fix_security_error(self, fixer):
        """Test security vulnerability fix"""
        result = await fixer._fix_security_error(
            {
                "vulnerable_package": "django",
                "vulnerable_version": "2.2.0",
                "cves": ["CVE-2021-12345"]
            },
            "Security vulnerability detected"
        )
        
        assert result["success"] is True
        assert result["fix_type"] == "security"
        assert "django" in result["suggestion"]["requirements.txt"]["package"]
    
    @pytest.mark.asyncio
    async def test_suggest_fix_unknown_type(self, fixer):
        """Test fix suggestion for unknown error type"""
        result = await fixer.suggest_fix(
            project_id=123,
            error_type="unknown",
            error_details={},
            job_log="Unknown error"
        )
        
        assert result["success"] is False
        assert "not automatically fixable" in result["reason"]
    
    @pytest.mark.asyncio
    async def test_create_fix_mr_branch_exists(self, fixer):
        """Test MR creation when branch already exists"""
        mock_response = MagicMock()
        mock_response.status = 400  # Branch exists
        
        # Create a proper mock for the session
        mock_session_instance = MagicMock()
        mock_post_context = MagicMock()
        mock_post_context.__aenter__.return_value = mock_response
        mock_post_context.__aexit__.return_value = None
        mock_session_instance.post.return_value = mock_post_context
        
        # Mock the ClientSession class itself
        with patch('aiohttp.ClientSession') as mock_session_class:
            # Make the class return our mock instance
            mock_context_manager = MagicMock()
            mock_context_manager.__aenter__.return_value = mock_session_instance
            mock_context_manager.__aexit__.return_value = None
            mock_session_class.return_value = mock_context_manager
            
            result = await fixer.create_fix_mr(
                None, 123, "main",
                {"error_type": "dependency", "missing_module": "test"}
            )
            
            assert result["success"] is False
            assert result["error"] == "branch_creation_failed"

class TestGitLabClientAdditional:
    """Additional tests for GitLab client coverage"""
    
    @pytest.fixture
    def client(self):
        return GitLabClient(token="test-token")
    
    @pytest.mark.asyncio
    async def test_get_pipeline_jobs_public_fallback(self, client):
        """Test pipeline jobs with public fallback"""
        # First call fails with auth, second succeeds without
        mock_response_auth = MagicMock()
        mock_response_auth.status = 401
        mock_response_auth.text = AsyncMock(return_value="Unauthorized")
        
        mock_response_public = MagicMock()
        mock_response_public.status = 200
        mock_response_public.json = AsyncMock(return_value=[{"id": 1}])
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            # Set up different responses for different calls
            mock_context_auth = MagicMock()
            mock_context_auth.__aenter__.return_value = mock_response_auth
            mock_context_auth.__aexit__.return_value = None
            
            mock_context_public = MagicMock()
            mock_context_public.__aenter__.return_value = mock_response_public
            mock_context_public.__aexit__.return_value = None
            
            mock_get.side_effect = [mock_context_auth, mock_context_public]
            
            jobs = await client.get_pipeline_jobs(123, 456)
            assert len(jobs) == 1
    
    @pytest.mark.asyncio
    async def test_create_commit_comment(self, client):
        """Test creating commit comment"""
        mock_response = MagicMock()
        mock_response.status = 201
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_context = MagicMock()
            mock_context.__aenter__.return_value = mock_response
            mock_context.__aexit__.return_value = None
            mock_post.return_value = mock_context
            
            success = await client.create_commit_comment(123, "abc123", "Test comment")
            assert success is True
    
    @pytest.mark.asyncio
    async def test_create_merge_request_note(self, client):
        """Test creating MR note"""
        mock_response = MagicMock()
        mock_response.status = 201
        
        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_context = MagicMock()
            mock_context.__aenter__.return_value = mock_response
            mock_context.__aexit__.return_value = None
            mock_post.return_value = mock_context
            
            success = await client.create_merge_request_note(123, 1, "Test note")
            assert success is True
    
    @pytest.mark.asyncio
    async def test_get_pipeline_details(self, client):
        """Test getting pipeline details"""
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": 123, "status": "failed"})
        
        with patch('aiohttp.ClientSession.get') as mock_get:
            mock_context = MagicMock()
            mock_context.__aenter__.return_value = mock_response
            mock_context.__aexit__.return_value = None
            mock_get.return_value = mock_context
            
            details = await client.get_pipeline_details(123, 456)
            assert details["id"] == 123

class TestFirestoreClientAdditional:
    """Additional tests for Firestore client coverage"""
    
    @pytest.fixture
    def client(self):
        with patch('app.firestore_client.default', return_value=(Mock(), "test-project")):
            with patch('app.firestore_client.firestore.Client'):
                return FirestoreClient()
    
    @pytest.mark.asyncio
    async def test_save_error_pattern_existing(self, client):
        """Test updating existing error pattern"""
        client.db = Mock()
        mock_doc = Mock()
        mock_doc.exists = True
        mock_doc_ref = Mock()
        mock_doc_ref.get.return_value = mock_doc
        client.db.collection().document.return_value = mock_doc_ref
        
        result = await client.save_error_pattern("dependency", {"module": "pandas"})
        assert result is True
        mock_doc_ref.update.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_daily_stats(self, client):
        """Test getting daily statistics"""
        client.db = Mock()
        
        # Mock the query results
        mock_doc = Mock()
        mock_doc.to_dict.return_value = {
            "timestamp": datetime.now(),
            "mr_created": True,
            "retry_success": False
        }
        
        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc]
        client.db.collection().where().where.return_value = mock_query
        
        stats = await client._get_daily_stats()
        assert len(stats) == 7  # Should return 7 days
    
    @pytest.mark.asyncio
    async def test_get_error_patterns(self, client):
        """Test getting error patterns"""
        client.db = Mock()
        
        mock_doc = Mock()
        mock_doc.to_dict.return_value = {
            "error_type": "dependency",
            "count": 10,
            "last_seen": datetime.now()
        }
        
        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc]
        client.db.collection().order_by().limit.return_value = mock_query
        
        patterns = await client._get_error_patterns()
        assert len(patterns) == 1
        assert patterns[0]["type"] == "dependency"
    
    @pytest.mark.asyncio
    async def test_cleanup_old_data(self, client):
        """Test cleanup of old data"""
        client.db = Mock()
        
        mock_doc = Mock()
        mock_ref = Mock()
        mock_doc.reference = mock_ref
        
        mock_query = Mock()
        mock_query.stream.return_value = [mock_doc, mock_doc]
        client.db.collection().where.return_value = mock_query
        
        count = await client.cleanup_old_data(30)
        assert count == 2
        assert mock_ref.delete.call_count == 2