"""Project commands for preparing, running, processing and publishing CHM output."""
import argparse
import json
from pathlib import Path
import sys
import subprocess

from .project import load_project, validate_inputs, validate_forcing
from .state import workspace, status


def parser():
    root = argparse.ArgumentParser(description='Run SnowCast projects independently of the tool checkout.')
    commands = root.add_subparsers(dest='action', required=True)
    for action in ('validate', 'prepare', 'met-update', 'run', 'postprocess', 'status'):
        command = commands.add_parser(action)
        command.add_argument('project', type=Path, help='Project directory or snowcast.json file')
        if action == 'validate':
            command.add_argument('--config-only', action='store_true', help='Validate structure without requiring external model inputs')
        if action == 'run':
            command.add_argument('--no-postprocess', action='store_true')
    command = commands.add_parser('publish', help='Publish one selected project and upload to its configured website',
                                  description='Generate COGs for one project selected by the site config and upload '
                                              'by default. Use --no-upload for local-only publication.')
    command.add_argument('config', type=Path, help='Authored site JSON')
    command.add_argument('--project', required=True, help='ID of one selected project')
    command.add_argument('--no-upload', action='store_true', help='Publish only to local staging; do not contact the webserver')
    command = commands.add_parser('deploy-ui', help='Deploy an already-built UI separately from model data')
    command.add_argument('--dist', type=Path, required=True)
    command.add_argument('--site-dir', type=Path, required=True)
    command = commands.add_parser('download-data', help='Download and verify a pinned observation source into the local cache')
    command.add_argument('dataset', help='Dataset ID in observations.json, e.g. canswe')
    command.add_argument('--registry', type=Path, help='Custom observation registry; defaults to the installed observations.json')
    command.add_argument('--cache', type=Path, help='Override SNOWCAST_DATA_CACHE or ~/.cache/snowcast/data')
    command.add_argument('--source', type=Path, help='Import an existing source download without network access')
    site = commands.add_parser('site', help='Configure a website and its observation datasets')
    actions = site.add_subparsers(dest='site_action', required=True)
    for action in ('validate', 'configure'):
        command = actions.add_parser(action)
        command.add_argument('config', type=Path, help='Authored site JSON')
        if action != 'validate':
            command.add_argument('--upload', action='store_true', help='Also update the configured webserver over SSH')
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == 'download-data':
            from .observation_data import download_data
            download_data(args.dataset, registry=args.registry, cache=args.cache, source=args.source)
            return 0
        if args.action in ('site', 'publish'):
            from .site_config import load_site, configure, publish_selected
            site = load_site(args.config)
            if args.action == 'publish':
                publish_selected(site, args.project, remote=not args.no_upload)
                destination = str(site.staging) if args.no_upload else f'{site.deploy["host"]}:{site.deploy["directory"]}'
                print(f'Published {args.project} to {destination}' + (' (local only; no upload)' if args.no_upload else ''))
                return 0
            if args.site_action == 'configure':
                configure(site, remote=args.upload)
            print(f'Site {args.site_action}: {site.spec["title"]}')
            return 0
        if args.action == 'deploy-ui':
            from .site import deploy_ui
            deploy_ui(args.dist, args.site_dir)
            print(f'Deployed UI to {args.site_dir}')
            return 0
        project = load_project(args.project)
        if args.action == 'validate':
            if not args.config_only:
                validate_inputs(project)
                from .chm_config import read_model, model_inputs
                model_inputs(project, read_model(project))
            print(f'Valid project {project.id}')
            return 0
        if args.action == 'status':
            file = project.work / 'status.json'
            value = json.loads(file.read_text()) if file.exists() else {'project': project.id, 'state': 'not_started'}
            print(json.dumps(value))
            return 0
        if args.action == 'met-update':
            validate_forcing(project)
        else:
            validate_inputs(project)
        from .jobs import resume_pending
        from .model import run_model
        from .rasters import postprocess
        with workspace(project):
            try:
                # Do not alter configuration or staging files used by a live PBS job.
                recovered = resume_pending(project.work, submit_model_chain=args.action == 'run')
                if 'completed' in recovered:
                    from .model import prune_checkpoints
                    prune_checkpoints(project)
                status(project, 'running', stage=args.action)
                if args.action == 'met-update':
                    from .forcing import update_forcing
                    detail = update_forcing(project)
                    status(project, 'met_updated', output=detail)
                    print(json.dumps(detail))
                    return 0
                if args.action == 'prepare':
                    from .model import prepare
                    config, _, _ = prepare(project)
                    status(project, 'prepared', config=str(config))
                    print(config)
                    return 0
                if args.action == 'run':
                    outcome = recovered[-1] if recovered else run_model(project)
                    if outcome == 'up_to_date' or args.no_postprocess:
                        status(project, outcome)
                        print(f'{project.id}: {outcome}')
                        return 0
                detail = postprocess(project)
                status(project, 'completed', output=detail)
                print(f'{project.id}: completed')
            except BaseException as error:
                status(project, 'failed', error=str(error), stage=args.action)
                from .notifications import notify_failure
                notify_failure(project, args.action, error)
                raise
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'SnowCast: {error}', file=sys.stderr)
        return 1
