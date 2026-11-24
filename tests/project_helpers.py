"""Independent project fixtures that may share explicitly referenced inputs."""
import json
from pathlib import Path


def clone_project(source, identifier):
    target = source.parent.parent / identifier / 'snowcast.json'
    if target.exists():
        return target
    raw = json.loads(source.read_text())
    raw.update(id=identifier, name=identifier.title())
    base = source.parent

    def absolute(section, key):
        if section.get(key) is not None:
            section[key] = str((base / section[key]).resolve())

    for field in ('config', 'overrides'):
        absolute(raw['model'], field)
    for section in (raw.get('forcing', {}),):
        for field in ('archive', 'index'):
            absolute(section, field)
    for key, value in raw['model'].get('assets', {}).items():
        raw['model']['assets'][key] = str((base / value).resolve())
    for section in (raw['model'], raw.get('postprocess', {})):
        absolute(section.get('job', {}), 'setup')
    absolute(raw.get('postprocess', {}), 'mesh')
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(raw))
    return target
