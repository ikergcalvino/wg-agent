import os

# api.config requires an API key at import time; this package is imported before conftest.py.
TEST_API_KEY = "test-api-key-0123456789"
os.environ["API_KEY"] = TEST_API_KEY
