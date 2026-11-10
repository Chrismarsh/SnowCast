"""The project CLI never runs the legacy plotting/upload pipeline implicitly."""
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
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.action == 'deploy-ui':
            from .site import deploy_ui
            deploy_ui(args.dist, args.site_dir)
            print(f'Deployed UI to {args.site_dir}')
            return 0
        project = load_project(args.project)
        if args.action == 'validate':
            if not args.config_only:
                validate_inputs(project)
                from .model import read_model
                read_model(project)
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
                resume_pending(project.work)
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
                    outcome = run_model(project)
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
