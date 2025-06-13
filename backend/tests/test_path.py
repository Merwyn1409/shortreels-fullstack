from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import fastapi

app = FastAPI()

print(f"FastAPI version: {fastapi.__version__}")
print(f"StaticFiles source: {StaticFiles.__module__}")

# Try mounting with name parameter
app.mount("/data", StaticFiles(directory=str(Path("data").resolve()), name="data"))

print("Mount successful!")