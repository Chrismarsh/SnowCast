import json
from pathlib import Path

import pytest

from snowcast_runner.cli import main
from snowcast_runner.model import read_model
from snowcast_runner.project import load_project


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))
    return path


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
    override.with_name('mesh.np1.partition').write_text('mesh')
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
        'mesh': str(project.model['overrides'].with_name('mesh.np1.partition')),
        'parameters': str(project.model['config'].with_name('parameters.json')),
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
        override.with_name(f'{name}.np{ranks}.partition').touch()
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
