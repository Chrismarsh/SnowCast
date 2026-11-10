"""Opt-in failure notifications. Credentials stay in the runner environment."""
import json
import os
import sys
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def notify_failure(project, domain, stage, error):
    variable = project.notifications.get('webhook_env')
    if not variable:
        return
    try:
        url = os.environ[variable]
        if urlsplit(url).scheme != 'https':
            raise ValueError('Webhook requires HTTPS')
        text = f'SnowCast {project.id}/{domain.id} failed during {stage}: {error}'
        request = Request(url, data=json.dumps({'text': text}).encode(), headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=10):
            pass
    except Exception:
        # Never mask the original failure or leak a credential URL in diagnostics.
        print('WARNING: failure notification could not be delivered; see domain status.json', file=sys.stderr)
