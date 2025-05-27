#!/usr/bin/env python3
"""
Run all tests with proper environment setup
"""

import os
import sys
import subprocess

def main():
    # Set test environment
    os.environ['TESTING'] = 'true'
    os.environ['GCP_PROJECT_ID'] = 'test-project-123'
    os.environ['GCP_LOCATION'] = 'us-central1'
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = ''
    
    print("🧪 Running ALL tests with coverage boost...")
    print("=" * 60)
    
    # Run all tests
    cmd = [
        sys.executable, '-m', 'pytest',
        'tests/',  # Run all test files
        '--cov=app',
        '--cov-report=term-missing',
        '--cov-report=html',
        '-v',
        '--tb=short'
    ]
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print("\n✅ All tests passed!")
        print("📊 Check htmlcov/index.html for detailed coverage report")
    else:
        print("\n❌ Some tests failed")
    
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())