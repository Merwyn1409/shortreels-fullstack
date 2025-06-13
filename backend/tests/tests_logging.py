import logging
import os
from pathlib import Path

def test_logging_setup():
    """Test that logging works in the test environment"""
    log_file = Path("/home/ubuntu/shortreels_v2/backend/logs/test.log")
    
    # Ensure directory exists
    log_file.parent.mkdir(exist_ok=True, parents=True)
    
    # Basic config with forced reset
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ],
        force=True
    )
    
    # Test logging
    logging.info("THIS IS A TEST LOG MESSAGE")
    
    # Verify file was created
    assert log_file.exists(), "Log file was not created"
    
    # Verify content
    with open(log_file) as f:
        content = f.read()
    assert "THIS IS A TEST LOG MESSAGE" in content, "Log message not found in file"