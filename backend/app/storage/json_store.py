"""Save complete runs atomically. Loading never executes an agent."""

import json
import re
import shutil
import tempfile
from pathlib import Path

from app.models.recording import Metadata, RecordedRun
from app.models.multi_recording import MultiMetadata, MultiRecordedRun

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "data" / "runs"


class RunStore:
    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = root

    def _path(self, run_id: str) -> Path:
        if not re.fullmatch(r"run-[a-zA-Z0-9-]+", run_id):
            raise ValueError("Invalid run ID.")
        return self.root / run_id

    def save(self, run: RecordedRun | MultiRecordedRun) -> Path:
        destination = self._path(run.metadata.run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise FileExistsError(destination)
        staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=self.root))
        try:
            # Publish the directory only after all three files are complete.
            for name, value in run.model_dump(mode="json").items():
                (staging / f"{name}.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            staging.rename(destination)
        finally:
            if staging.exists():
                shutil.rmtree(staging)
        return destination

    def load(self, run_id: str) -> RecordedRun | MultiRecordedRun:
        directory = self._path(run_id)
        if not directory.is_dir():
            raise FileNotFoundError(run_id)
        try:
            data = {
                name: json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
                for name in ("metadata", "events", "states")
            }
            version = data["metadata"].get("schema_version", 1)
            if version not in (1, 2):
                raise ValueError("Unsupported recording schema version.")
            run = (MultiRecordedRun if version == 2 else RecordedRun).model_validate(data)
        except FileNotFoundError as exc:
            raise ValueError("Recording is incomplete.") from exc
        if run.metadata.run_id != run_id:
            raise ValueError("Recording ID does not match its directory.")
        return run

    def list_runs(self, schema_version: int | None = None) -> list[Metadata | MultiMetadata]:
        if not self.root.exists():
            return []
        # Ignore staging directories. Validate each published recording before listing it.
        runs = [self.load(path.name).metadata for path in self.root.iterdir()
                if path.is_dir() and re.fullmatch(r"run-[a-zA-Z0-9-]+", path.name)]
        return sorted((run for run in runs if schema_version is None or run.schema_version == schema_version),
                      key=lambda item: (item.created_at, item.run_id), reverse=True)
