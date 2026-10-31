"""Deployment state machine; adapters keep failure/replay tests independent of AWS."""
from datetime import datetime, timezone
from contract import require, sha
from diagnostics import diagnostic
import json


def now():
    return datetime.now(timezone.utc).isoformat()


def execute(request, adapter):
    fingerprint = sha(json.dumps(request, sort_keys=True).encode())
    previous = adapter.load(request['DeploymentId'])
    if previous:
        require(previous['requestFingerprint'] == fingerprint, 'DeploymentId already belongs to another request')
        require(previous['status'] != 'RUNNING', 'Interrupted deployment: reconcile recorded state before a new DeploymentId')
        adapter.publish(previous)
        return previous
    receipt = {'deploymentId': request['DeploymentId'], 'requestFingerprint': fingerprint,
               'artifact': {k: request[k] for k in ('ArtifactKey','ArtifactVersionId','ArtifactSha256')},
               'startedAt': now(), 'status': 'RUNNING', 'failureStage': None,
               'previousRevision': None, 'attemptedRevision': None, 'activeRevision': None,
               'rollbackResult': 'NOT_NEEDED', 'migrationCompatibility': None}
    adapter.save(receipt)
    adapter.publish(receipt)
    stage = 'preflight'
    before = None
    mutated = False
    try:
        manifest = adapter.preflight(request)
        receipt.update(applicationSourceCommit=manifest['applicationSourceCommit'],
                       deploymentConfigCommit=manifest['deploymentConfigCommit'],
                       releaseVersion=manifest['releaseVersion'], migrationCompatibility=manifest['migrationCompatibility'])
        before = adapter.current()
        receipt['previousRevision'] = before['revision']
        receipt['previousRelease'] = before.get('release')
        receipt['previousArtifact'] = before.get('artifact')
        receipt['activeRevision'] = before['revision']
        require(before['revision'] == int(request['ExpectedPreviousRevision']), 'Stale expected revision')
        require(before['status'] in ('absent','deployed'), 'Release not in a deployable state')
        adapter.secret_gate()
        stage = 'upgrade'
        receipt['attemptedRevision'] = before['revision'] + 1
        adapter.save(receipt)
        adapter.publish(receipt)
        mutated = True
        adapter.upgrade()
        stage = 'smoke'
        receipt['smoke'] = {}
        adapter.smoke(receipt['smoke'])
        final = adapter.current()
        require(final['status'] == 'deployed' and final['revision'] > before['revision'], 'Upgrade did not produce a deployed revision')
        receipt.update(status='SUCCESS', activeRevision=final['revision'])
    except Exception as error:
        # Never persist subprocess output/exceptions: Kubernetes/Helm output can contain secrets.
        receipt.update(status='FAILED', failureStage=stage, diagnostic=diagnostic(error))
        if mutated:
            try:
                if before['revision']:
                    if not adapter.matches(before):
                        adapter.rollback(before['revision'])
                    require(adapter.matches(before), 'Rollback verification failed')
                    receipt['rollbackSmoke'] = {}
                    adapter.smoke(receipt['rollbackSmoke'])
                    receipt['rollbackResult'] = 'VERIFIED'
                else:
                    receipt['rollbackResult'] = 'NO_PREVIOUS_RELEASE'
                receipt['activeRevision'] = adapter.current()['revision']
            except Exception as error:
                receipt.update(rollbackResult='FAILED_OR_UNKNOWN', activeRevision=None, rollbackDiagnostic=diagnostic(error))
    receipt['finishedAt'] = now()
    # Only a verified transition can update provenance. Historical replay above
    # publishes the operation result, never the active marker.
    if receipt['status'] == 'SUCCESS' or (receipt['rollbackResult'] == 'VERIFIED' and receipt['activeRevision'] != receipt['previousRevision']):
        adapter.activate(receipt)
    adapter.save(receipt)
    adapter.publish(receipt)
    return receipt
