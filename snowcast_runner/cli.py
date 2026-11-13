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
    for action in ('validate', 'prepare', 'met-update', 'run', 'postprocess', 'publish', 'status'):
        command = commands.add_parser(action)
        command.add_argument('project', type=Path, help='Project directory or snowcast.json file')
        if action == 'validate':
            command.add_argument('--config-only', action='store_true', help='Validate structure without requiring external model inputs')
        if action == 'run':
            command.add_argument('--no-postprocess', action='store_true')
        if action == 'publish':
            command.add_argument('--site-dir', type=Path, required=True, help='Local or mounted site root')
    command = commands.add_parser('deploy-ui', help='Deploy an already-built UI separately from model data')
    command.add_argument('--dist', type=Path, required=True)
    command.add_argument('--site-dir', type=Path, required=True)
    site = commands.add_parser('site', help='Configure a website and publish its selected projects')
    actions = site.add_subparsers(dest='site_action', required=True)
    for action in ('validate', 'configure', 'publish'):
        command = actions.add_parser(action)
        command.add_argument('config', type=Path, help='Authored site JSON')
        if action != 'validate':
            command.add_argument('--upload', action='store_true', help='Also update the configured webserver over SSH')
        if action == 'publish':
            command.add_argument('--project', required=True, help='ID of one selected project')
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == 'site':
            from .site_config import load_site, configure, publish_selected
            site = load_site(args.config)
            if args.site_action == 'configure':
                configure(site, remote=args.upload)
            elif args.site_action == 'publish':
                publish_selected(site, args.project, remote=args.upload)
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
        elif args.action != 'publish':
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
                if args.action == 'publish':
                    from .site import publish_project
                    catalogue = publish_project(project, args.site_dir)
                    status(project, 'published', latest_time=catalogue['latest_time'])
                    print(f'Published {project.id} to {args.site_dir}')
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
