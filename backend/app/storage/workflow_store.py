"""Store workflow recordings atomically without invoking the application again."""
import json
import os
import re
import tempfile
from pathlib import Path
from app.models.workflow import WorkflowRecording

DEFAULT_ROOT = Path(__file__).resolve().parents[3] / 'data' / 'workflows'


class WorkflowStore:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = root

    def _path(self, run_id):
        if not re.fullmatch(r'workflow-[a-zA-Z0-9-]+', run_id):
            raise ValueError('Invalid workflow ID.')
        return self.root / f'{run_id}.json'

    def save(self, recording: WorkflowRecording):
        recording = WorkflowRecording.model_validate(recording.model_dump(mode='json'))
        destination = self._path(recording.metadata.run_id)
        self.root.mkdir(parents=True, exist_ok=True)
        # Publish a complete file with an exclusive hard link; never replace an existing recording.
        fd, name = tempfile.mkstemp(prefix='.pending-', dir=self.root)
        try:
            with os.fdopen(fd, 'w') as file:
                file.write(recording.model_dump_json(indent=2))
            os.link(name, destination)
        finally:
            os.unlink(name)
        return destination

    def load(self, run_id):
        result = WorkflowRecording.model_validate(json.loads(self._path(run_id).read_text()))
        if result.metadata.run_id != run_id:
            raise ValueError('Workflow ID does not match its file.')
        return result

    def list_runs(self):
        if not self.root.exists():
            return []
        return sorted((self.load(path.stem).metadata for path in self.root.glob('workflow-*.json')),
                      key=lambda item: (item.created_at, item.run_id), reverse=True)
