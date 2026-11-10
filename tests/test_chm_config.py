import json
from pathlib import Path
import sys

import pytest

from snowcast_runner.cli import main
from snowcast_runner.model import read_model
from snowcast_runner.project import load_project


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


def partition(path, ranks=1):
    entries = {field: [f'{path.name}.meshes/rank-{rank}_{field}.h5' for rank in range(ranks)]
               for field in ('meshes', 'parameters')}
    for paths in entries.values():
        for name in paths:
            data = path.parent / name
            data.parent.mkdir(parents=True, exist_ok=True)
            data.write_text(f'fixture {name}')
    return write(path, {'ranks': str(ranks), 'max_ghost_distance': '100',
                        'num_global_faces': str(ranks), 'local_sizes': ['1'] * ranks, **entries})


@pytest.fixture
def project_file(tmp_path):
    shared = tmp_path / 'shared'
    base = write(shared / 'base.json', {
        'meshes': {'mesh': 'missing-base-mesh.np800.partition', 'parameters': 'parameters.json'},
        'modules': ['solar', 'FSM', 'snow_slide'],
        'config': {'FSM': {'keep': 1, 'replace': 2}, 'snow_slide': {'enabled': True}},
        'remove_depency': {'snow_slide': 'FSM'},
        'output': {'output_dir': '/must/not/write/here', 'ugrid': {'variables': ['wrong'], 'specific_time': '23:00'}},
        'forcing': {'file': '/must/not/read/here'},
        'option': {'startdate': '19900101T000000'},
        'checkpoint': {'auto_resume': True},
    })
    (shared / 'parameters.json').write_text('{}')
    folder = tmp_path / 'projects' / 'west'
    override = write(folder / 'chm' / 'local.json', {
        'meshes': {'mesh': 'mesh.np1.partition'},
        'modules': ['solar', 'FSM'],
        'config': {'FSM': {'replace': 3}},
    })
    partition(override.with_name('mesh.np1.partition'))
    (shared / 'forcing.nc').touch()
    write(shared / 'metadata.json', [{'file_name': 'forcing.nc', 'start_time': '20260901T000000', 'end_time': '20260902T000000'}])
    return write(folder / 'snowcast.json', {
        'version': 2, 'id': 'west', 'name': 'Western test',
        'model': {'config': str(base), 'overrides': 'chm/local.json', 'start_date': '2026-09-01',
                  'remove': ['/config/snow_slide', '/remove_depency/snow_slide']},
        'forcing': {'index': str(shared / 'metadata.json')},
        'postprocess': {'variables': ['swe']},
    })


def test_merge_before_mesh_validation_and_preserve_declaring_paths(project_file, monkeypatch, tmp_path):
    project = load_project(project_file)
    authored = {p: p.read_bytes() for p in (project.file, project.model['config'], project.model['overrides'])}
    monkeypatch.chdir(tmp_path.parent)
    assert main(['validate', str(project_file)]) == 0
    assert not project.work.exists()
    assert main(['prepare', str(project_file)]) == 0
    config = json.loads((project.work / 'chm/config.json').read_text())
    assert config['modules'] == ['solar', 'FSM']
    assert config['config'] == {'FSM': {'keep': 1, 'replace': 3}}
    assert config['remove_depency'] == {}
    assert config['meshes'] == {
        'mesh': str(project.work / 'chm/mesh.np1.partition'),
        'parameters': str(project.work / 'chm/parameters.json'),
    }
    assert config['forcing']['file'] == str(project.work / 'met/index.json')
    assert config['option']['startdate'] == '20260901T000000'
    assert config['output'] == {'output_dir': str(project.work / 'chm/output'),
                                'ugrid': {'variables': ['swe'], 'specific_time': '23:00'}}
    assert config['checkpoint'] == {'auto_resume': True}
    assert all(p.read_bytes() == before for p, before in authored.items())


def test_missing_override_mesh_reports_project_key_origin_and_path(project_file, capsys):
    project = load_project(project_file)
    mesh = project.model['overrides'].with_name('mesh.np1.partition')
    mesh.unlink()
    assert main(['validate', str(project_file)]) == 1
    error = capsys.readouterr().err
    for text in ('west', 'meshes.mesh', str(project.model['overrides']), str(mesh), 'mesh input missing'):
        assert text in error
    assert not project.work.exists()


def test_final_override_partition_count_is_checked(project_file, capsys):
    project = load_project(project_file)
    mesh = project.model['overrides'].with_name('mesh.np2.partition')
    mesh.touch()
    write(project.model['overrides'], {'meshes': {'mesh': mesh.name}})
    assert main(['validate', str(project_file)]) == 1
    assert 'mesh partition ranks (2) do not match model.job.ranks (1)' in capsys.readouterr().err
    assert not project.work.exists()


@pytest.mark.parametrize('pointer', ['/missing', '/config/FSM/typo', '/modules/0', '/config/bad~2key'])
def test_bad_removal_fails_before_staging(project_file, pointer, capsys):
    raw = json.loads(project_file.read_text())
    raw['model']['remove'] = [pointer]
    write(project_file, raw)
    assert main(['prepare', str(project_file)]) == 1
    assert 'model.remove' in capsys.readouterr().err
    assert not (project_file.parent / 'work/chm').exists()
    assert not (project_file.parent / 'work/met').exists()


def test_json5_null_values_and_pointer_escaping(project_file):
    project = load_project(project_file)
    project.model['overrides'].write_text('''{
        // Local JSON5 fragment; trailing commas are accepted.
        meshes: {mesh: 'mesh.np1.partition'},
        config: {FSM: {replace: null, 'a/b~c': 5}},
    }''')
    raw = json.loads(project_file.read_text())
    raw['model']['remove'] += ['/config/FSM/a~1b~0c']
    write(project_file, raw)
    assert read_model(load_project(project_file))['config']['FSM'] == {'keep': 1, 'replace': None}


def test_three_projects_share_base_but_choose_their_own_mesh_modules_and_jobs(project_file):
    base_project = load_project(project_file)
    base_before = base_project.model['config'].read_bytes()
    raw = json.loads(project_file.read_text())
    manifests = []
    for name, ranks, modules in [('west', 1, ['solar', 'FSM']), ('tvc', 2, ['FSM']), ('third', 3, ['FSM', 'fetchr'])]:
        folder = project_file.parent.parent / name
        override = folder / 'chm/local.json'
        write(override, {'meshes': {'mesh': f'{name}.np{ranks}.partition'}, 'modules': modules})
        partition(override.with_name(f'{name}.np{ranks}.partition'), ranks)
        settings = json.loads(json.dumps(raw))
        settings.update(id=name)
        settings['model']['job'] = {'mode': 'pbs', 'nodes': 1, 'cpus_per_node': ranks,
                                  'ranks_per_node': ranks, 'ranks': ranks, 'launcher': ['mpirun', '-n', '{ranks}']}
        settings['postprocess']['job'] = {'mode': 'local', 'ranks': 1}
        manifest = write(folder / 'snowcast.json', settings)
        assert main(['prepare', str(manifest)]) == 0
        p = load_project(manifest)
        config = json.loads((p.work / 'chm/config.json').read_text())
        assert config['modules'] == modules
        assert Path(config['meshes']['mesh']).name == f'{name}.np{ranks}.partition'
        assert config['output']['output_dir'] == str(p.work / 'chm/output')
        assert p.postprocess['job']['ranks'] == 1
        assert not (p.work / 'jobs').exists()
        manifests.append(p)
    assert len({p.work for p in manifests}) == 3
    assert base_project.model['config'].read_bytes() == base_before


def test_asset_alias_does_not_replace_project_display_name(project_file):
    raw = json.loads(project_file.read_text())
    raw['model']['assets'] = {'shared_inputs': str(project_file.parent.parent.parent / 'shared')}
    write(project_file, raw)
    assert load_project(project_file).name == 'Western test'


def test_partition_inputs_are_readable_from_the_model_job_cwd(project_file, monkeypatch, tmp_path):
    project = load_project(project_file)
    source = project.model['overrides'].with_name('mesh.np1.partition')
    authored = {p: p.read_bytes() for p in source.parent.rglob('*') if p.is_file()}
    script = project_file.parent / 'read_partition.py'
    script.write_text('''
import json
from pathlib import Path
import sys
cwd = Path.cwd()
config = json.loads(Path(sys.argv[1]).read_text())
partition = Path(config['meshes']['mesh'])
assert partition.parent == cwd and partition.is_symlink()
metadata = json.loads(partition.read_text())
for field in ('meshes', 'parameters'):
    for entry in metadata[field]:
        assert Path(entry).read_text() == f'fixture {entry}'
assert Path(config['meshes']['parameters']).read_text() == '{}'
(cwd / 'output/clean_exit').touch()
''')
    raw = json.loads(project_file.read_text())
    raw['model']['command'] = [sys.executable, str(script), '{config}']
    write(project_file, raw)
    monkeypatch.chdir(tmp_path.parent)
    assert main(['prepare', str(project_file)]) == 0
    cwd = project.work / 'chm'
    links = [cwd / source.name, cwd / f'{source.name}.meshes', cwd / 'parameters.json']
    assert all(p.is_symlink() for p in links)
    assert links[0].resolve() == source
    assert links[1].resolve() == source.with_name(f'{source.name}.meshes')
    inodes = [p.lstat().st_ino for p in links]
    assert main(['run', str(project_file), '--no-postprocess']) == 0
    assert (cwd / 'output/clean_exit').is_file()
    assert [p.lstat().st_ino for p in links] == inodes
    assert all(p.read_bytes() == before for p, before in authored.items())


@pytest.mark.parametrize('entry', ['domain.mesh', './nested/inputs/domain.mesh', 'absolute'])
def test_partition_file_references_keep_their_layout(project_file, entry):
    project = load_project(project_file)
    source = project.model['overrides'].with_name('mesh.np1.partition')
    if entry == 'absolute':
        entry = str(project_file.parent / 'external/domain.mesh')
    mesh = source.parent / entry
    mesh.parent.mkdir(parents=True, exist_ok=True)
    mesh.write_bytes(b'opaque mesh bytes')
    write(source, {'ranks': 1, 'meshes': [entry]})  # Parameters are optional.
    assert main(['prepare', str(project_file)]) == 0
    cwd = project.work / 'chm'
    assert (cwd / entry).read_bytes() == b'opaque mesh bytes'
    if Path(entry).is_absolute():
        assert not (cwd / mesh.name).exists()
    else:
        assert (cwd / Path(entry).parts[0]).is_symlink()


@pytest.mark.parametrize('field', ['meshes', 'parameters'])
@pytest.mark.parametrize('action', ['validate', 'prepare'])
def test_missing_partition_dependency_fails_before_staging(project_file, field, action, capsys):
    project = load_project(project_file)
    source = project.model['overrides'].with_name('mesh.np1.partition')
    metadata = json.loads(source.read_text())
    missing = source.parent / metadata[field][0]
    missing.unlink()
    assert main([action, str(project_file)]) == 1
    error = capsys.readouterr().err
    for text in (str(source), field, str(missing), 'partition input missing'):
        assert text in error
    assert not (project.work / 'chm').exists()
    assert not (project.work / 'met').exists()


@pytest.mark.parametrize(('metadata', 'error'), [
    ({'ranks': 2, 'meshes': ['x', 'y']}, 'ranks (2) do not match'),
    ({'ranks': True, 'meshes': ['x']}, 'ranks must be a positive integer'),
    ({'ranks': 1, 'meshes': []}, 'meshes must list one file per rank'),
    ({'ranks': 1, 'meshes': ['x'], 'parameters': 'y'}, 'parameters must list one file per rank'),
    ({'ranks': 1, 'meshes': [None]}, 'expected a nonempty file path'),
])
def test_invalid_partition_metadata_is_reported(project_file, metadata, error, capsys):
    project = load_project(project_file)
    source = project.model['overrides'].with_name('mesh.np1.partition')
    source.with_name('x').touch()
    write(source, metadata)
    assert main(['validate', str(project_file)]) == 1
    assert error in capsys.readouterr().err
    assert not project.work.exists()


@pytest.mark.parametrize('entry', ['../external.mesh', 'output/domain.mesh', 'config.json'])
def test_partition_cannot_redirect_managed_run_paths(project_file, entry, capsys):
    project = load_project(project_file)
    source = project.model['overrides'].with_name('mesh.np1.partition')
    dependency = source.parent / entry
    dependency.parent.mkdir(parents=True, exist_ok=True)
    dependency.touch()
    write(source, {'ranks': 1, 'meshes': [entry]})
    assert main(['prepare', str(project_file)]) == 1
    assert ('relative paths must stay below' if '..' in entry else 'reserved model input name') in capsys.readouterr().err
    assert not (project.work / 'chm').exists()


@pytest.mark.parametrize('conflict', ['asset', 'file', 'directory', 'symlink', 'dangling_symlink'])
def test_partition_input_conflicts_leave_existing_inputs_untouched(project_file, conflict, capsys):
    project = load_project(project_file)
    name = 'mesh.np1.partition.meshes'
    other = project_file.parent / 'other'
    other.mkdir()
    cwd = project.work / 'chm'
    target = cwd / name
    if conflict == 'asset':
        raw = json.loads(project_file.read_text())
        raw['model']['assets'] = {name: str(other)}
        write(project_file, raw)
    else:
        cwd.mkdir(parents=True)
        if conflict == 'file':
            target.write_text('do not replace')
        elif conflict == 'directory':
            target.mkdir()
        else:
            target.symlink_to(other if conflict == 'symlink' else other / 'missing')
        inode = target.lstat().st_ino
    assert main(['prepare', str(project_file)]) == 1
    assert ('name collision' if conflict == 'asset' else 'destination already exists') in capsys.readouterr().err
    assert not (cwd / 'mesh.np1.partition').exists()
    assert not (project.work / 'met').exists()
    if conflict != 'asset':
        assert target.lstat().st_ino == inode


def test_projects_can_stage_different_meshes_with_the_same_names(project_file):
    from project_helpers import clone_project
    first = load_project(project_file)
    second_file = clone_project(project_file, 'tvc')
    override = second_file.parent / 'chm/local.json'
    write(override, {'meshes': {'mesh': 'mesh.np1.partition'}})
    source = partition(override.with_name('mesh.np1.partition'))
    raw = json.loads(second_file.read_text())
    raw['model']['overrides'] = str(override)
    write(second_file, raw)
    second = load_project(second_file)
    assert main(['prepare', str(project_file)]) == 0
    assert main(['prepare', str(second_file)]) == 0
    first_link = first.work / 'chm/mesh.np1.partition'
    second_link = second.work / 'chm/mesh.np1.partition'
    assert first_link.resolve() == first.model['overrides'].with_name(source.name)
    assert second_link.resolve() == source
    assert first_link.resolve() != second_link.resolve()
