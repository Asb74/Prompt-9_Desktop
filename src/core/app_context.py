from dataclasses import dataclass
from pathlib import Path

from src.utils.paths import assets_dir, data_dir, icons_dir, logs_dir, project_root


@dataclass(slots=True)
class AppContext:
    settings: object
    project_root: Path
    assets_dir: Path
    data_dir: Path
    logs_dir: Path
    icons_dir: Path

    @classmethod
    def create(cls, settings: object) -> "AppContext":
        return cls(
            settings=settings,
            project_root=project_root(),
            assets_dir=assets_dir(),
            data_dir=data_dir(),
            logs_dir=logs_dir(),
            icons_dir=icons_dir(),
        )
