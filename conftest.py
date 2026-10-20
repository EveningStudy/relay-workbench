"""Legacy suites use project-relative paths; keep each suite in its own root."""
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def project_directory(request, monkeypatch):
    root=Path(__file__).parent
    project='voice' if 'voice' in request.path.parts else 'scene_robot'
    monkeypatch.chdir(root/project)
    for folder in ['results','data/logs','assets/scan']:
        Path(folder).mkdir(parents=True,exist_ok=True)
