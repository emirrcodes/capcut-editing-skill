"""Explicit human non-speech review is bound to the current draft fingerprint."""
import copy
from unittest.mock import patch
import unittest
import test_workflow as fixtures
from test_workflow import draft, project, tool
from draft_primitives import apply_timeline_keep_ranges
from speech_verify import compare

class ReviewedGapTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown
    def setup_gap(self,ranges):
        folder=project(self.root,draft(self.media,(2_000_000,)))
        snapshot=tool.snapshot(folder,tool.source_paths(folder))
        self.config['speech_reviewed_gaps']={'draft_sha256':snapshot['draft_info.json']['sha256'],'ranges_us':ranges,'basis':'user-confirmed'}
        tool.validate_settings(self.config)
        return folder
    def analysis(self):
        return {'method':'test-vad','audio_duration_us':2_000_000,'speech_ranges_us':[[0,2_000_000]],'keep_ranges_us':[[0,2_000_000]],'conservatively_protected_ranges_us':[],'gap_reviews':[]}
    def test_explicit_review_removes_detector_positive_interval(self):
        folder=self.setup_gap([[500_000,1_000_000]])
        with patch('speech_scan.analyze',return_value=self.analysis()):
            tool.prepare(folder,'speech',self.root/'work',self.config)
        result=tool.read_json(self.root/'work/prepared.json')
        self.assertEqual(result['duration'],1_500_000)
        self.assertEqual(result['tracks'][0]['segments'][1]['source_timerange'],{'start':1_000_000,'duration':1_000_000})
        self.assertEqual(tool.read_json(folder/'draft_info.json')['duration'],2_000_000)
    def test_review_cannot_be_reused_after_draft_changes(self):
        folder=self.setup_gap([[500_000,1_000_000]])
        for path in tool.draft_paths(folder):path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(RuntimeError,'another draft version'):
            tool.prepare(folder,'speech',self.root/'stale-work',self.config)
        self.assertFalse((self.root/'stale-work').exists())
    def test_model_inference_cannot_claim_user_confirmation(self):
        self.setup_gap([[500_000,1_000_000]])
        self.config['speech_reviewed_gaps']['basis']='vad-inferred'
        with self.assertRaisesRegex(RuntimeError,'user-confirmed'):
            tool.validate_settings(self.config)
    def test_reviewed_gap_keeps_micro_clip_protection(self):
        folder=self.setup_gap([[50_000,1_950_000]])
        with patch('speech_scan.analyze',return_value=self.analysis()):
            tool.prepare(folder,'speech',self.root/'protected-work',self.config)
        result=tool.read_json(self.root/'protected-work/prepared.json')
        self.assertEqual([s['target_timerange']['duration'] for s in result['tracks'][0]['segments']],[100_000,100_000])
    def test_verification_reports_authorized_override_separately(self):
        value=draft(self.media,(2_000_000,));analysis=self.analysis()
        analysis.update({'keep_ranges_us':[[0,500_000],[1_000_000,2_000_000]],'reviewed_non_speech_ranges_us':[[500_000,1_000_000]]})
        report=compare({'segments':[]},{'segments':[]},value,self.root,analysis)
        self.assertEqual(report['vad_supported_source_loss_us'],500_000)
        self.assertEqual(report['user_reviewed_vad_override_us'],500_000)
        self.assertEqual(report['unexpected_vad_supported_source_loss_us'],0)
