import copy
from pathlib import Path
import sys
import unittest
from validate_r5 import snapshot, validate

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'operations'))
from events import baseline_decision, fingerprint


class R5Tests(unittest.TestCase):
    def test_contract(self):
        validate(snapshot())

    def test_dead_publisher_regression(self):
        data = snapshot()
        data['iam'] = data['iam'].replace('"sqs:ReceiveMessage"', '"events:PutEvents"')
        with self.assertRaises(AssertionError):
            validate(data)

    def test_http_publish_regression(self):
        data = snapshot(); data['tracking_http'] += '\npublisher.PublishAsync();'
        with self.assertRaises(AssertionError):
            validate(data)

    def test_sequence_and_identity_regressions(self):
        for field, old, new in (
            ('outbox_model', 'entity.HasKey(x => x.EventId)', 'entity.HasKey(x => x.AggregateId)'),
            ('contract', 'long SequenceNumber', 'long RemovedField'),
            ('processor', 'return Result(TrackingEventHandlingOutcome.WaitingPredecessor);', 'dbContext.ProcessedEvents.Add(new ProcessedEvent());'),
            ('processor', 'shipment.LastProcessedTrackingSequence + 1', 'shipment.Version + 1'),
            ('shipment_sources', 'namespace ', '// ShipmentCreated\nnamespace '),
        ):
            with self.subTest(field=field):
                data = snapshot(); self.assertIn(old, data[field]); data[field] = data[field].replace(old, new)
                with self.assertRaises(AssertionError): validate(data)

    def test_baseline_new_empty_only(self):
        report = {'shipment': {'LastProcessedTrackingSequence': None, 'Status': 'CREATED', 'LastTrackingEventAt': None}, 'tracking': []}
        self.assertEqual(0, baseline_decision(report))
        report['shipment']['Status'] = 'DELIVERED'
        with self.assertRaises(ValueError): baseline_decision(report)

    def test_historical_prefix_requires_review_and_rejects_gaps(self):
        report = {'shipment': {'LastProcessedTrackingSequence': None}, 'tracking': [{'SequenceNumber': 1}, {'SequenceNumber': 2}]}
        with self.assertRaises(ValueError): baseline_decision(report)
        self.assertEqual(2, baseline_decision(report, 2))
        with self.assertRaises(ValueError): baseline_decision(report, 1)
        report['tracking'][1]['SequenceNumber'] = 3
        with self.assertRaises(ValueError): baseline_decision(report, 2)

    def test_review_token_detects_drift(self):
        before = {'shipment': {'Version': 3}, 'tracking': []}
        after = copy.deepcopy(before); after['shipment']['Version'] = 4
        self.assertNotEqual(fingerprint(before), fingerprint(after))

    def test_active_baseline_is_never_overwritten(self):
        with self.assertRaises(ValueError):
            baseline_decision({'shipment': {'LastProcessedTrackingSequence': 5}}, 0)
