# tests/test_multi_language.py
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from app.ai_analyzer import AIAnalyzer
from app.vertex_ai_fixer import VertexAIFixer

class TestMultiLanguageSupport:
    """Test multi-language detection and fixes"""
    
    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance"""
        with patch('app.ai_analyzer.vertexai.init'):
            with patch('app.ai_analyzer.GenerativeModel'):
                return AIAnalyzer()
    
    @pytest.fixture
    def fixer(self):
        """Create fixer instance"""
        return VertexAIFixer(token="test-token")
    
    class TestLanguageDetection:
        """Test language detection for various languages"""
        
        def test_detect_typescript(self, analyzer):
            """Test TypeScript detection"""
            log = """
            TSError: ⨯ Unable to compile TypeScript:
            src/index.ts:10:5 - error TS2322: Type 'string' is not assignable to type 'number'.
            """
            assert analyzer.detect_language(log, "ts-compile") == "typescript"
        
        def test_detect_rust(self, analyzer):
            """Test Rust detection"""
            log = """
            error[E0308]: mismatched types
             --> src/main.rs:5:5
            error: aborting due to previous error
            """
            assert analyzer.detect_language(log, "cargo-build") == "rust"
        
        def test_detect_php(self, analyzer):
            """Test PHP detection"""
            log = """
            Fatal error: Uncaught Error: Class 'App\\Controller' not found
            composer install failed
            """
            assert analyzer.detect_language(log, "php-test") == "php"
        
        def test_detect_csharp(self, analyzer):
            """Test C# detection"""
            log = """
            error CS0246: The type or namespace name 'System.Linq' could not be found
            dotnet build failed
            """
            assert analyzer.detect_language(log, "dotnet-build") == "csharp"
        
        def test_detect_mixed_logs(self, analyzer):
            """Test detection when multiple language indicators present"""
            # Python should win with more indicators
            log = """
            npm install
            File "test.py", line 10
            SyntaxError: invalid syntax
            pytest failed
            """
            assert analyzer.detect_language(log, "mixed-test") == "python"
    
    class TestLanguageSpecificFixes:
        """Test fixes for different languages"""
        
        @pytest.mark.asyncio
        async def test_typescript_dependency_fix(self, fixer):
            """Test TypeScript dependency fix"""
            # TypeScript is treated as JavaScript internally
            result = await fixer.suggest_fix(
                project_id=123,
                error_type="dependency",
                error_details={
                    "missing_module": "@types/node",
                    "language": "javascript",  # TypeScript uses JavaScript handling
                    "package_manager": "npm"
                },
                job_log="Cannot find module '@types/node'"
            )
            
            assert result["success"] is True
            assert "package.json" in result["suggestion"]
            assert "@types/node" in result["explanation"]
        
        @pytest.mark.asyncio
        async def test_rust_dependency_fix(self, fixer):
            """Test Rust dependency fix"""
            result = await fixer.suggest_fix(
                project_id=123,
                error_type="dependency",
                error_details={
                    "missing_module": "tokio",
                    "language": "rust"
                },
                job_log="unresolved import `tokio`"
            )
            
            assert result["success"] is True
            assert result["confidence"] >= 0.7
            assert "rust" in result["explanation"].lower()
        
        @pytest.mark.asyncio
        async def test_java_gradle_dependency_fix(self, fixer):
            """Test Java Gradle dependency fix"""
            result = await fixer.suggest_fix(
                project_id=123,
                error_type="dependency",
                error_details={
                    "missing_module": "org.springframework.boot",
                    "language": "java",
                    "build_tool": "gradle"
                },
                job_log="package org.springframework.boot does not exist"
            )
            
            assert result["success"] is True
            assert "build.gradle" in result["suggestion"]
            assert "springframework" in result["explanation"]
        
        @pytest.mark.asyncio
        async def test_generic_language_fallback(self, fixer):
            """Test fallback for unsupported language"""
            result = await fixer.suggest_fix(
                project_id=123,
                error_type="dependency",
                error_details={
                    "missing_module": "some-module",
                    "language": "kotlin"  # Not explicitly supported
                },
                job_log="Unresolved reference: some-module"
            )
            
            assert result["success"] is True
            assert result["suggestion"]["manual"] is True
            assert "kotlin" in result["explanation"].lower()
    
    class TestCommitGeneration:
        """Test commit generation for different languages"""
        
        @pytest.mark.asyncio
        async def test_create_javascript_fix_commit(self, fixer):
            """Test JavaScript dependency fix commit"""
            # Create a proper mock context manager
            mock_response = MagicMock()
            mock_response.status = 201
            
            mock_session = MagicMock()
            mock_context_manager = MagicMock()
            mock_context_manager.__aenter__.return_value = mock_response
            mock_context_manager.__aexit__.return_value = None
            mock_session.post.return_value = mock_context_manager
            
            fix_data = {
                "error_type": "dependency",
                "language": "javascript",
                "missing_module": "express",
                "package_manager": "npm"
            }
            
            result = await fixer._create_fix_commit(
                mock_session, 123, "fix-branch", fix_data
            )
            
            assert result is True
            # Verify the commit was attempted
            mock_session.post.assert_called()
            call_args = mock_session.post.call_args
            assert "express" in str(call_args)
        
        @pytest.mark.asyncio
        async def test_create_go_fix_commit(self, fixer):
            """Test Go module fix commit"""
            # Create a proper mock context manager
            mock_response = MagicMock()
            mock_response.status = 201
            
            mock_session = MagicMock()
            mock_context_manager = MagicMock()
            mock_context_manager.__aenter__.return_value = mock_response
            mock_context_manager.__aexit__.return_value = None
            mock_session.post.return_value = mock_context_manager
            
            fix_data = {
                "error_type": "dependency",
                "language": "go",
                "missing_module": "github.com/gin-gonic/gin"
            }
            
            result = await fixer._create_fix_commit(
                mock_session, 123, "fix-branch", fix_data
            )
            
            assert result is True
            call_args = mock_session.post.call_args
            assert "go get" in str(call_args)
            assert "gin-gonic/gin" in str(call_args)

# tests/test_edge_cases.py
import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.ai_analyzer import AIAnalyzer

class TestEdgeCases:
    """Test edge cases and error handling"""
    
    @pytest.fixture
    def analyzer(self):
        with patch('app.ai_analyzer.vertexai.init'):
            with patch('app.ai_analyzer.GenerativeModel'):
                return AIAnalyzer()
    
    def test_empty_log_handling(self, analyzer):
        """Test handling of empty logs"""
        assert analyzer.detect_language("", "") == "python"  # Should default to Python
    
    def test_very_large_log_handling(self, analyzer):
        """Test handling of very large logs"""
        # Create a 10MB log
        large_log = "Error line\n" * 500000
        cleaned = analyzer._clean_log(large_log)
        # Should truncate to reasonable size
        assert len(cleaned.split('\n')) <= 200
    
    def test_malformed_log_handling(self, analyzer):
        """Test handling of logs with special characters"""
        log = "\x00\x01\x02 Binary content 🚀 Unicode मराठी"
        # Should not crash
        language = analyzer.detect_language(log, "test")
        assert language in ["python", "javascript", "java", "go", "ruby", "php", "rust", "csharp", "typescript"]
    
    @pytest.mark.asyncio
    async def test_ai_timeout_handling(self, analyzer):
        """Test handling when AI takes too long"""
        analyzer.model = Mock()
        # Create a proper mock that returns a value, not a coroutine
        analyzer.model.generate_content = Mock(side_effect=TimeoutError())
        
        result = await analyzer.analyze_failure("test log", "test job")
        # Should fall back to simple analysis
        assert result["error_category"] == "other"
        assert result["recommended_action"] == "manual_fix"