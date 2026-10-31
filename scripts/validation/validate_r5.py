"""Small source guards; PostgreSQL behavioral tests live in EventReliability.Tests."""
from pathlib import Path
import json
import re
import sys
import xml.etree.ElementTree as ET
import hcl2
import yaml

ROOT = Path(__file__).resolve().parents[2]


def snapshot():
    return {
        'iam': (ROOT/'infra/live/dev/iam/terragrunt.hcl').read_text(),
        'shipment_project': (ROOT/'microservices/shipment-service/src/ShipmentService.Infrastructure/ShipmentService.Infrastructure.csproj').read_text(),
        'tracking_http': (ROOT/'microservices/tracking-service/src/TrackingService.Infrastructure/Services/TrackingEventsService.cs').read_text(),
        'outbox_model': (ROOT/'microservices/tracking-service/src/TrackingService.Infrastructure/Persistence/TrackingDbContext.cs').read_text(),
        'processor': (ROOT/'microservices/shipment-service/src/ShipmentService.Infrastructure/Services/TrackingEventProcessor.cs').read_text(),
        'contract': (ROOT/'microservices/tracking-service/src/TrackingService.Application/Contracts/Events/TrackingStatusUpdatedEventData.cs').read_text(),
        'shipment_sources': '\n'.join(p.read_text(encoding='utf-8-sig') for p in (ROOT/'microservices/shipment-service/src').rglob('*.cs') if not {'bin','obj'}.intersection(p.parts)),
        'ci': (ROOT/'.github/workflows/validate.yml').read_text(),
    }


def validate(data):
    iam = hcl2.loads(data['iam'])
    # Scope to this workload; Tracking legitimately retains PutEvents.
    roles = iam['inputs']['roles']
    shipment = json.dumps(next(role for name, role in roles.items() if 'shipment-service-irsa' in name))
    assert 'events:PutEvents' not in shipment, 'Shipment must not publish dead events'
    assert 'sqs:ChangeMessageVisibility' in shipment, 'Ordering retry requires visibility permission'
    assert 'events:PutEvents' in data['iam'], 'Tracking publication permission missing'
    project = ET.fromstring(data['shipment_project'])
    assert not any(p.get('Include') == 'AWSSDK.EventBridge' for p in project.iter('PackageReference')), 'Dead publisher dependency'
    assert 'publisher.' not in data['tracking_http'] and 'PutEvents' not in data['tracking_http'], 'HTTP path must not publish'
    assert 'OutboxMessages.Add' in data['tracking_http'], 'Business transaction must persist outbox'
    assert 'ShipmentCreated' not in data['shipment_sources'] and 'ShipmentStatusChanged' not in data['shipment_sources'], 'Dead Shipment event publication'
    assert 'entity.HasKey(x => x.EventId)' in data['outbox_model'], 'Outbox requires unique EventId'
    assert 'AggregateSequence' in data['outbox_model'], 'Missing aggregate sequence'
    assert 'long SequenceNumber' in data['contract'], 'V2 must carry sequence'
    processor = data['processor']
    assert 'shipment.Version' not in processor, 'Metadata version is not the tracking sequence'
    future = re.search(r'if \(envelope.Data.SequenceNumber > shipment.LastProcessedTrackingSequence \+ 1\)\s*return Result\(TrackingEventHandlingOutcome.WaitingPredecessor\);', processor)
    assert future and future.end() < processor.index('dbContext.ProcessedEvents.Add'), 'Future sequence must return without inbox mutation'
    ci = yaml.safe_load(data['ci'])['jobs']['postgres-r5-reliability']
    assert ci['services']['postgres']['image'] == 'postgres:15.18'
    steps = json.dumps(ci['steps'])
    assert 'R5_POSTGRES_DSN' in steps and 'postgres_gate.py trx' in steps and 'dotnet test' in steps, 'Real PostgreSQL tests cannot silently skip'
    return iam


if __name__ == '__main__':
    try:
        validate(snapshot())
        print('R5 event reliability source contracts: PASS')
    except (AssertionError, KeyError, IndexError) as error:
        print(f'R5 contract failure: {error}', file=sys.stderr)
        sys.exit(1)
