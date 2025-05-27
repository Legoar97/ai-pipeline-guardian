#!/bin/bash
# AI Pipeline Guardian - Test Runner Script

echo "🧪 AI Pipeline Guardian - Running Test Suite"
echo "==========================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Install test dependencies if not installed
echo -e "${YELLOW}📦 Installing test dependencies...${NC}"
pip install -r requirements-test.txt

# Run linting (optional)
echo -e "\n${YELLOW}🔍 Running code quality checks...${NC}"
python -m flake8 app/ --max-line-length=120 --ignore=E501,W503 || true

# Run unit tests
echo -e "\n${YELLOW}🧪 Running unit tests...${NC}"
pytest tests/test_ai_analyzer.py tests/test_vertex_ai_fixer.py tests/test_gitlab_client.py tests/test_firestore_client.py -v -m "not integration and not performance"

# Run integration tests
echo -e "\n${YELLOW}🔗 Running integration tests...${NC}"
pytest tests/test_main.py tests/test_integration.py -v -m "not performance"

# Run performance tests
echo -e "\n${YELLOW}⚡ Running performance tests...${NC}"
pytest tests/test_performance.py -v

# Run all tests with coverage
echo -e "\n${YELLOW}📊 Running all tests with coverage report...${NC}"
pytest --cov=app --cov-report=term-missing --cov-report=html

# Check if tests passed
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed!${NC}"
    echo -e "${GREEN}📊 Coverage report available in htmlcov/index.html${NC}"
else
    echo -e "\n${RED}❌ Some tests failed!${NC}"
    exit 1
fi

# Display coverage summary
echo -e "\n${YELLOW}📈 Coverage Summary:${NC}"
coverage report

echo -e "\n${GREEN}🎉 Test suite execution completed!${NC}"