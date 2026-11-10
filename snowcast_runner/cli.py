"""The project CLI never runs the legacy plotting/upload pipeline implicitly."""
import argparse
import json
from pathlib import Path
import sys
import subprocess

from .project import load_project, validate_inputs
from .state import workspace, status


def parser():
    root = argparse.ArgumentParser(description='Run SnowCast projects independently of the tool checkout.')
    commands = root.add_subparsers(dest='action', required=True)
    for action in ('validate', 'prepare', 'run', 'postprocess', 'publish', 'status'):
        command = commands.add_parser(action)
        command.add_argument('project', type=Path, help='Project directory or snowcast.json file')
        command.add_argument('--domain')
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
                from .model import read_model, model_inputs
                for domain in project.domains:
                    model_inputs(domain, read_model(domain))
            print(f'Valid project {project.id}: {", ".join(d.id for d in project.domains)}')
            return 0
        if args.action == 'status':
            domains = [project.domain(args.domain)] if args.domain else project.domains
            for d in domains:
                file = d.work / 'status.json'
                value = json.loads(file.read_text()) if file.exists() else {'domain': d.id, 'state': 'not_started'}
                print(json.dumps(value))
            return 0
        domain = project.domain(args.domain)
        if args.action != 'publish':
            validate_inputs(project, domains=[domain])
        from .jobs import resume_pending
        from .model import run_model
        from .rasters import postprocess
        with workspace(project, domain):
            try:
                # Do not alter configuration or staging files used by a live PBS job.
                resume_pending(domain.work)
                status(domain, 'running', stage=args.action)
                if args.action == 'prepare':
                    from .model import prepare
                    config, _, _ = prepare(domain)
                    status(domain, 'prepared', config=str(config))
                    print(config)
                    return 0
                if args.action == 'publish':
                    from .site import publish_domain
                    catalogue = publish_domain(project, domain, args.site_dir)
                    status(domain, 'published', latest_time=catalogue['latest_time'])
                    print(f'Published {domain.id} to {args.site_dir}')
                    return 0
                if args.action == 'run':
                    outcome = run_model(domain)
                    if outcome == 'up_to_date' or args.no_postprocess:
                        status(domain, outcome)
                        print(f'{domain.id}: {outcome}')
                        return 0
                detail = postprocess(domain)
                status(domain, 'completed', output=detail)
                print(f'{domain.id}: completed')
            except BaseException as error:
                status(domain, 'failed', error=str(error), stage=args.action)
                from .notifications import notify_failure
                notify_failure(project, domain, args.action, error)
                raise
        return 0
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(f'SnowCast: {error}', file=sys.stderr)
        return 1
