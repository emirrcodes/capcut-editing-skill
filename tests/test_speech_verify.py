"""Tight pauses, preserved source evidence, repeats, and ordered slice checks."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from test_workflow import draft, tool
from test_speech_words import segment
from draft_primitives import apply_timeline_keep_ranges
import speech_verify
import speech_scan

class CutVerificationTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown
    def analysis(self, keep):
        return {'keep_ranges_us':keep, 'speech_ranges_us':[[0,700_000],[1_300_000,2_000_000]], 'conservatively_protected_ranges_us':[]}
    def test_missing_token_with_retained_source_is_not_speech_loss(self):
        value=draft(self.media,(2_000_000,))
        transcript={'segments':[segment(0,2,[('panzehir',0,2)])]}
        report=speech_verify.compare(transcript,{'segments':[]},value,self.root,self.analysis([[0,700_000],[1_300_000,2_000_000]]))
        self.assertEqual(report['vad_supported_source_loss_us'],0)
        changed=report['changed_or_missing_words'][0]
        self.assertEqual(changed['word_interval_kept_us'],1_400_000)
        self.assertEqual(changed['source_ranges'][0]['retained_source_ranges_us'],[[0,700_000],[1_300_000,2_000_000]])
    def test_repeated_token_is_reported_without_authorizing_deletion(self):
        value=draft(self.media,(2_000_000,))
        before={'segments':[segment(0,2,[('abi',0,.5),('abi',1,1.5)])]}
        after={'segments':[segment(0,.5,[('abi',0,.5)])]}
        report=speech_verify.compare(before,after,value,self.root,self.analysis([[0,2_000_000]]))
        self.assertEqual(len(report['changed_or_missing_words']),1)
        self.assertEqual(report['changed_or_missing_words'][0]['word_interval_kept_us'],500_000)
        self.assertEqual(report['vad_supported_source_loss_us'],0)
    def test_source_shift_is_refused_even_when_recognition_matches(self):
        value=draft(self.media,(2_000_000,)); keep=[(0,700_000),(1_300_000,2_000_000)]
        candidate=copy.deepcopy(value);apply_timeline_keep_ranges(candidate,keep)
        self.assertEqual(speech_verify.validate_sources(value,candidate,self.root,keep),2)
        candidate['tracks'][0]['segments'][1]['source_timerange']['start']-=100_000
        with self.assertRaisesRegex(RuntimeError,'source mapping'):
            speech_verify.validate_sources(value,candidate,self.root,keep)
    def test_verify_rejects_supported_audio_loss_and_keeps_report(self):
        value=draft(self.media,(2_000_000,)); keep=[(0,500_000),(1_300_000,2_000_000)]
        candidate=copy.deepcopy(value);apply_timeline_keep_ranges(candidate,keep)
        work=self.root/'verify';work.mkdir()
        before={'segments':[segment(0,2,[('word',0,2)])]}
        tool.write_json(work/'speech-word-transcript.json',before)
        with patch.object(speech_verify,'transcribe',return_value=before):
            with self.assertRaisesRegex(RuntimeError,'VAD-supported'):
                speech_verify.verify(value,candidate,self.root,self.analysis(keep),self.media,self.config,work)
        self.assertTrue((work/'speech-cut-verification.json').exists())
    def test_source_occurrences_cannot_be_swapped_to_cover_a_repeat(self):
        value=draft(self.media)
        value['tracks'][0]['segments'][1]['source_timerange']['start']=0
        keep=[(0,400_000),(1_500_000,1_900_000)]
        candidate=copy.deepcopy(value);apply_timeline_keep_ranges(candidate,keep)
        self.assertEqual(speech_verify.validate_sources(value,candidate,self.root,keep),2)
        pieces=candidate['tracks'][0]['segments']
        pieces[0]['source_timerange'],pieces[1]['source_timerange']=pieces[1]['source_timerange'],pieces[0]['source_timerange']
        with self.assertRaisesRegex(RuntimeError,'source mapping'):
            speech_verify.validate_sources(value,candidate,self.root,keep)
    def test_one_microsecond_resave_rounding_is_supported_without_retiming(self):
        value=draft(self.media,(2_000_000,))
        value['tracks'][0]['segments'][0]['source_timerange']['duration']+=1
        tool.check_editable(value,'speech')
        keep=[(200_000,800_000),(1_400_000,1_900_000)]
        candidate=copy.deepcopy(value);apply_timeline_keep_ranges(candidate,keep)
        self.assertEqual(speech_verify.validate_sources(value,candidate,self.root,keep),2)
        value['tracks'][0]['segments'][0]['source_timerange']['duration']+=1
        with self.assertRaisesRegex(RuntimeError,'forward 1.0x'):
            tool.check_editable(value,'speech')
    def test_verification_requires_current_word_review(self):
        self.config['speech_verify_cut']=True
        with self.assertRaisesRegex(RuntimeError,'requires speech_word_review'):
            tool.validate_settings(self.config)

@unittest.skipUnless(speech_scan.available(),'Run setup.py')
class TightPauseTests(unittest.TestCase):
    def test_tight_profile_removes_90ms_gap_while_default_preserves_it(self):
        import numpy as np
        path=Path(__file__).resolve().parents[1]/'skills/capcut-editing/references/speech-tight.config.json'
        tight=tool.settings(path); default=tool.settings()
        samples=np.zeros(2*speech_scan.RATE,dtype=np.float32)
        def detector(samples,threshold,config):
            return [(0,12800),(15200,28800)] if threshold==.5 else []
        with patch.object(speech_scan,'detect',side_effect=detector):
            strict=speech_scan.analyze_samples(samples,tight)
            natural=speech_scan.analyze_samples(samples,default)
        self.assertIn([830_000,920_000],strict['removed_ranges_us'])
        self.assertEqual(natural['removed_ranges_us'],[])
        self.assertEqual(tight['speech_min_gap'],.08)
        self.assertEqual(tight['speech_padding'],.03)
