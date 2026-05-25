from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def assets_dir() -> Path:
    return project_root() / "assets"


def data_dir() -> Path:
    path = project_root() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = project_root() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def icons_dir() -> Path:
    return assets_dir() / "icons"


def attachments_dir() -> Path:
    path = data_dir() / "attachments"
    path.mkdir(parents=True, exist_ok=True)
    return path
