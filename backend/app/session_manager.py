import os
import shutil

def cleanup_session(file_path):
    if os.path.exists(file_path):
        os.remove(file_path)
