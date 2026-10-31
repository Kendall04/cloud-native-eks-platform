"""R5 operator-only PostgreSQL recovery. Never called by an HTTP endpoint.

DSN comes from R5_OPERATOR_DSN, never a CLI argument or log. Use the R3
operator/migrator credential and verify-full TLS outside a disposable localhost DB.
"""
import argparse
import hashlib
import json
import os
import sys
from uuid import UUID


METADATA = '"EventId", "AggregateId", "AggregateSequence", "EventType", "EventVersion", "CreatedAt", "PublishedAt", "Attempts", "NextAttemptAt", "LastError", "FailedAt", "LeaseUntil"'


def fingerprint(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True, default=str).encode()).hexdigest()


def baseline_decision(report, reviewed_sequence=None):
    if report['shipment']['LastProcessedTrackingSequence'] is not None:
        raise ValueError('Baseline already set; never overwrite an active sequence')
    sequences = [r['SequenceNumber'] for r in report['tracking']]
    if sequences != list(range(1, len(sequences) + 1)):
        raise ValueError('Historical tracking is not a contiguous prefix; operator investigation required')
    shipment = report['shipment']
    if not sequences and shipment['Status'] == 'CREATED' and shipment['LastTrackingEventAt'] is None:
        if reviewed_sequence not in (None, 0):
            raise ValueError('Invalid empty baseline')
        return 0
    if not sequences or reviewed_sequence != len(sequences):
        raise ValueError('Ambiguous historical state: review every event and explicitly approve the full closed prefix')
    return reviewed_sequence


def baseline_report(connection, shipment_id):
    shipment = connection.execute('SELECT "Id", "Status", "Version", "LastTrackingEventAt", "LastProcessedTrackingSequence" FROM shipment."Shipments" WHERE "Id"=%s FOR UPDATE', (shipment_id,)).fetchone()
    if not shipment:
        raise ValueError('Shipment not found')
    # Prevent a writer from extending this prefix between review validation and commit.
    connection.execute('LOCK TABLE tracking."TrackingEvents" IN SHARE MODE')
    tracking = connection.execute('SELECT "Id", "SequenceNumber", "Status", "OccurredAt" FROM tracking."TrackingEvents" WHERE "ShipmentId"=%s ORDER BY "SequenceNumber"', (shipment_id,)).fetchall()
    pending = connection.execute('SELECT count(*) AS count FROM tracking."OutboxMessages" WHERE "AggregateId"=%s', (shipment_id,)).fetchone()['count']
    if pending:
        raise ValueError('V2 outbox already exists; do not baseline over active events')
    return {'shipment': shipment, 'tracking': tracking}


def run(connection, args):
    if args.command == 'list-failed':
        return connection.execute(f'SELECT {METADATA} FROM tracking."OutboxMessages" WHERE "FailedAt" IS NOT NULL ORDER BY "FailedAt", "EventId" LIMIT 100').fetchall()
    if args.command == 'inspect':
        return connection.execute(f'SELECT {METADATA} FROM tracking."OutboxMessages" WHERE "EventId"=%s', (args.event_id,)).fetchone()
    if args.command == 'requeue':
        result = connection.execute('''UPDATE tracking."OutboxMessages" SET "FailedAt"=NULL,
            "Attempts"=0, "NextAttemptAt"=clock_timestamp(), "LeaseToken"=NULL, "LeaseUntil"=NULL
            WHERE "EventId"=%s AND "FailedAt" IS NOT NULL AND "PublishedAt" IS NULL
              AND ("LeaseUntil" IS NULL OR "LeaseUntil" <= clock_timestamp())
            RETURNING "EventId", "AggregateId", "AggregateSequence", "Attempts"''', (args.event_id,)).fetchone()
        if not result:
            raise ValueError('Not an inactive failed unpublished event; no change')
        return {'operation': 'requeue', **result}
    report = baseline_report(connection, args.shipment_id)
    if args.command == 'baseline-report':
        return {'reviewToken': fingerprint(report), **report}
    if args.review_token != fingerprint(report):
        raise ValueError('Review token does not match current data; repeat review')
    sequence = baseline_decision(report, args.reviewed_sequence)
    connection.execute('UPDATE shipment."Shipments" SET "LastProcessedTrackingSequence"=%s, "Version"="Version"+1 WHERE "Id"=%s', (sequence, args.shipment_id))
    return {'operation': 'baseline', 'shipmentId': args.shipment_id, 'sequence': sequence, 'reviewToken': args.review_token}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list-failed')
    for name in ('inspect', 'requeue'):
        commands.add_parser(name).add_argument('--event-id', type=UUID, required=True)
    for name in ('baseline-report', 'baseline'):
        p = commands.add_parser(name)
        p.add_argument('--shipment-id', type=UUID, required=True)
        if name == 'baseline':
            p.add_argument('--review-token', required=True)
            p.add_argument('--reviewed-sequence', type=int, help='Explicit operator attestation: every event in this prefix was definitively reconciled')
    args = parser.parse_args()
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    from psycopg.rows import dict_row
    dsn = os.environ.get('R5_OPERATOR_DSN', '')
    config = conninfo_to_dict(dsn)
    if not dsn or (config.get('host') not in ('127.0.0.1', 'localhost') and config.get('sslmode') != 'verify-full'):
        raise ValueError('Operator DSN required; remote PostgreSQL requires verify-full TLS')
    with psycopg.connect(dsn, row_factory=dict_row) as connection:
        connection.execute("SET LOCAL lock_timeout = '5s'")
        connection.execute("SET LOCAL statement_timeout = '15s'")
        result = run(connection, args)
    # Print only after commit; metadata deliberately excludes payload, credentials and locations.
    print(json.dumps(result, default=str, indent=2))


if __name__ == '__main__':
    try:
        main()
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
    except Exception:
        # DB exceptions may contain connection or business data.
        print('Recovery failed; no successful transaction reported. Check operator access and database availability.', file=sys.stderr)
        sys.exit(1)
