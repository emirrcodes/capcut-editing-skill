import unittest
from unittest.mock import patch
import speech_pauses
import capcut_tool as tool


def w(text,start=0,end=100000):
    return {"word":text,"start_us":start,"end_us":end}


def record(voice=(), words=(), suspects=()):
    return {"core_us":[0,2000000],"voice_keep_us":list(voice),"word_protection_us":list(words),"suspect_ranges_us":list(suspects)}


class PauseReviewTests(unittest.TestCase):
    def test_independent_short_weak_word_start_is_not_overridden_by_vad(self):
        records=[{"recovered_words":[w("bana",29900000,30300000)],"suspect_ranges_us":[]}]
        self.assertEqual(speech_pauses.short_word_guards(records,60000000),[(29880000,30320000)])
    def test_stretched_local_word_cannot_restore_entire_noise_pause(self):
        records=[{"recovered_words":[w("veya",50400000,51860000)],"suspect_ranges_us":[]}]
        self.assertEqual(speech_pauses.short_word_guards(records,60000000),[])
    def test_suspect_short_decode_is_not_a_trusted_short_word_guard(self):
        records=[{"recovered_words":[w("bana",100000,300000)],"suspect_ranges_us":[[0,500000]]}]
        self.assertEqual(speech_pauses.short_word_guards(records,2000000),[])
    def test_low_confidence_local_text_cannot_anchor_a_cut(self):
        result={"segments":[{"start":0,"end":1,"avg_logprob":-2.3,
                             "no_speech_prob":0,"words":[{"word":"zaten","start":.2,"end":.5}]}]}
        words,suspects=speech_pauses.window_words(result,2000000,0)
        self.assertEqual(words,[])
        self.assertEqual(suspects,[(0,1000000)])
    def test_distant_same_word_cannot_anchor_an_unresolved_occurrence(self):
        prefix=[w("hani"),w("bu"),w("benim"),w("sözüm")]
        self.assertFalse(speech_pauses.anchored([w("hani")],prefix,[w("bana")])[0])
    def test_declined_context_review_reports_only_actually_retained_audio(self):
        decisions=[{"range_us":[600000,900000],"status":"no-additional-cut"}]
        self.assertEqual(speech_pauses.retained_declines(decisions,[(0,700000),(800000,2000000)],2000000),[(600000,700000),(800000,900000)])
    def test_single_context_cannot_authorize_cut(self):
        _, ranges, _ = speech_pauses.classify([record()],2000000,80000)
        self.assertEqual(ranges,[])
    def test_any_context_voice_vetoes_cut(self):
        _, ranges, _ = speech_pauses.classify([record(),record([(0,2000000)])],2000000,80000)
        self.assertEqual(ranges,[])
    def test_suspect_decode_vetoes_cut(self):
        _, ranges, _ = speech_pauses.classify([record(),record(suspects=[(0,2000000)])],2000000,80000)
        self.assertEqual(ranges,[])
    def test_stretched_words_are_candidates_for_anchor_review(self):
        _, ranges, _ = speech_pauses.classify([record(words=[(0,2000000)]),record()],2000000,80000)
        self.assertEqual(ranges,[(0,2000000)])
    def test_word_after_gap_is_retained_despite_early_timestamp(self):
        accepted,_ = speech_pauses.anchored([w("bana")],[w("harcamak")],[w("bana"),w("inanılmaz")])
        self.assertTrue(accepted)
    def test_missing_crossing_word_never_authorizes_cut(self):
        accepted,_ = speech_pauses.anchored([w("hani")],[w("harcamak")],[w("bana")])
        self.assertFalse(accepted)
    def test_same_token_on_both_sides_is_ambiguous(self):
        accepted,_ = speech_pauses.anchored([w("ama")],[w("ama")],[w("ama")])
        self.assertFalse(accepted)
    def test_missing_side_anchor_stays(self):
        self.assertFalse(speech_pauses.anchored([w("bana")],[],[w("bana")])[0])
    def test_invalid_segment_does_not_hide_unrelated_words(self):
        result={"segments":[{"start":0,"end":1,"words":[{"word":"bana","start":0,"end":.5}]},
                            {"start":1,"end":1.5,"words":[{"word":"hani","start":1.2,"end":1.2}]}]}
        words,suspects=speech_pauses.window_words(result,2000000,0)
        self.assertEqual([x["word"] for x in words],["bana"])
        self.assertEqual(suspects,[(1000000,1500000)])
    def test_context_review_requires_candidate_source_verification(self):
        config=tool.settings();config["speech_verify_cut"]=False
        with self.assertRaisesRegex(RuntimeError,"requires"):
            tool.validate_settings(config)
    def test_eighty_ms_pause_threshold_is_separate_from_clip_guard(self):
        _, ranges, _=speech_pauses.classify([record([(0,100000),(180000,2000000)]),record([(0,100000),(180000,2000000)])],2000000,80000)
        self.assertEqual(ranges,[(100000,180000)])


import test_workflow as fixtures


class PauseIntegrationTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown

    def run_review(self, raw_speech, crossing="bana", anchor="bana", base_keep=None, rechecks=(), crossing_bounds=(200000,1200000)):
        work=self.root/"pause-integration";work.mkdir()
        tool.write_json(work/"speech-long-word-rechecks.json",{"windows":list(rechecks)})
        analysis={"audio_duration_us":2000000,"keep_ranges_us":base_keep if base_keep is not None else [[0,2000000]],
                  "speech_ranges_us":raw_speech,"conservatively_protected_ranges_us":[]}
        result={"segments":[{"start":0,"end":.3,"words":[{"word":"anchor","start":.1,"end":.3}]}]}
        records=[{"range_us":[0,2000000],"core_us":[0,2000000],"voice_keep_us":[],
                  "word_protection_us":[],"words":[w(crossing,*crossing_bounds)],"suspect_ranges_us":[]}]*2
        def side_words(result,duration,offset):
            if offset==900000:return [w(anchor,1000000,1200000)],[]
            return [w("harcamak",200000,400000)],[]
        with patch.object(speech_pauses,"detect",return_value=[]), \
             patch.object(speech_pauses,"transcribe",return_value=result), \
             patch.object(speech_pauses,"window_words",side_effect=side_words), \
             patch.object(speech_pauses,"classify",return_value=([{"coverage":2}],[(600000,900000)],[])), \
             patch.object(speech_pauses,"read_audio",return_value=[0]*32000):
            # Local words are injected to represent an approximate crossing word.
            def classify(found,*args):
                for record in found:record["words"]=[w(crossing,*crossing_bounds)]
                return [{"coverage":2}],[(600000,900000)],[]
            with patch.object(speech_pauses,"classify",side_effect=classify):
                return speech_pauses.review(self.media,analysis,self.config,work)

    def test_local_consensus_cannot_override_global_vad_source_audio(self):
        report=self.run_review([[600000,900000]])
        self.assertEqual(report["keep_ranges_us"],[[0,2000000]])
        self.assertEqual(report["pause_review"]["confirmed_non_speech_ranges_us"],[])

    def test_resolved_complete_word_allows_cut_of_stretched_time_only(self):
        report=self.run_review([[0,500000],[1000000,2000000]])
        self.assertEqual(report["keep_ranges_us"],[[0,600000],[900000,2000000]])
        self.assertEqual(report["pause_review"]["confirmed_non_speech_ranges_us"],[(600000,900000)])

    def test_unresolved_word_keeps_source_even_with_negative_vad(self):
        report=self.run_review([[0,500000],[1000000,2000000]],crossing="hani",anchor="bana")
        self.assertEqual(report["keep_ranges_us"],[[0,2000000]])
        self.assertEqual(report["pause_review"]["kept_uncertain_ranges_us"],[[600000,900000]])

    def test_independent_weak_word_guard_restores_a_base_vad_omission(self):
        records=[{"recovered_words":[w("bana",600000,900000)],"suspect_ranges_us":[]}]
        report=self.run_review([[0,500000],[1000000,2000000]],
                               base_keep=[[0,600000],[900000,2000000]],rechecks=records)
        self.assertEqual(report["keep_ranges_us"],[[0,2000000]])

    def test_two_uncropped_contexts_restore_weak_word_before_pause_cut(self):
        report=self.run_review([[0,500000],[1300000,2000000]],
                               base_keep=[[0,600000],[900000,2000000]],crossing_bounds=(600000,1160000))
        self.assertEqual(report["keep_ranges_us"],[[0,2000000]])
        self.assertEqual(report["pause_review"]["independent_context_word_protection_us"],[(580000,1180000)])
        self.assertEqual(report["pause_review"]["confirmed_non_speech_ranges_us"],[])
