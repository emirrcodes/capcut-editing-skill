"""Final publication regressions: malformed alignments and stale pause spans."""
import unittest
from unittest.mock import patch
import test_workflow as fixtures
from test_speech_words import segment
from test_speech_pauses import w
import capcut_tool as tool
import speech_words
import speech_pauses


class SegmentQuarantineTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown

    def test_zero_word_quarantines_only_its_segment(self):
        value={"segments":[segment(0,.3,[("sol",.1,.3)]),segment(.6,1,[("bozuk",.8,.8)]),segment(1.3,1.8,[("sağ",1.5,1.7)])]}
        words,suspects=speech_words.segment_words(value,2_000_000)
        self.assertEqual([w["word"] for w in words],["sol","sağ"])
        self.assertEqual(suspects,[(600_000,1_000_000)])

    def test_missing_or_nonfinite_word_times_keep_bounded_segment(self):
        for word in ({"word":"bozuk","start":.8},{"word":"bozuk","start":float("nan"),"end":1}):
            value={"segments":[{"start":.6,"end":1,"words":[word]}]}
            self.assertEqual(speech_words.segment_words(value,2_000_000),([],[(600_000,1_000_000)]))

    def test_invalid_segment_bounds_still_stop(self):
        value={"segments":[segment(.8,.8,[("bozuk",.8,.8)])]}
        with self.assertRaisesRegex(RuntimeError,"ASR timestamp"):speech_words.segment_words(value,2_000_000)

    def test_recheck_recovers_bounded_words_without_changing_other_segments(self):
        work=self.root/"invalid-word";work.mkdir()
        analysis={"audio_duration_us":2_000_000,"keep_ranges_us":[[0,300_000]],"speech_ranges_us":[[0,300_000]],"conservatively_protected_ranges_us":[]}
        original={"segments":[segment(0,.3,[("sol",0,.3)]),segment(1,1.4,[("bozuk",1.2,1.2)])]}
        retry={"segments":[segment(.4,.8,[("gerçek",.4,.7)])]}
        with patch.object(speech_words,"transcribe",side_effect=[original,retry]) as engine:
            result=speech_words.review(self.media,analysis,self.config,work)
        self.assertEqual(engine.call_count,2)
        self.assertEqual(result["word_review"]["suspect_ranges_us"],[[1_000_000,1_400_000]])
        self.assertEqual(result["word_review"]["unresolved_kept_ranges_us"],[])
        self.assertIn([980_000,1_320_000],result["keep_ranges_us"])

    def test_unresolved_invalid_word_is_preserved_with_one_bounded_recheck(self):
        work=self.root/"invalid-kept";work.mkdir()
        analysis={"audio_duration_us":2_000_000,"keep_ranges_us":[[0,300_000]],"speech_ranges_us":[[0,300_000]],"conservatively_protected_ranges_us":[]}
        original={"segments":[segment(0,.3,[("sol",0,.3)]),segment(1,1.4,[("bozuk",1.2,1.2)])]}
        retry={"segments":[segment(.4,.8,[("bozuk",.6,.6)])]}
        with patch.object(speech_words,"transcribe",side_effect=[original,retry]) as engine:
            result=speech_words.review(self.media,analysis,self.config,work)
        self.assertEqual(engine.call_count,2)
        self.assertEqual(result["word_review"]["unresolved_kept_ranges_us"],[[1_000_000,1_400_000]])
        self.assertIn([1_000_000,1_400_000],result["keep_ranges_us"])


class CrossingRefinementTests(unittest.TestCase):
    def evidence(self,shorts=((1_780_000,2_160_000),)):
        return [{"word":w("bana",a,b),"guard_us":[a-20_000,b+20_000],"context_index":i} for i,(a,b) in enumerate(shorts)]

    def test_guarded_uncropped_interval_resolves_stretched_boundary(self):
        original=w("bana",820_000,2_160_000)
        words,records=speech_pauses.refine_crossing_words([original],self.evidence())
        self.assertEqual(words,[w("bana",1_780_000,2_160_000)])
        self.assertEqual(records[0]["original_word"],original)
        self.assertEqual(records[0]["context_guards_us"],[[1_760_000,2_180_000]])
        effective=[w for w in words if w["start_us"]<1_760_000 and w["end_us"]>1_110_000]
        accepted,_=speech_pauses.anchored(effective,[w("harcamak")],[w("inanılmaz")])
        self.assertTrue(accepted)

    def test_short_crossing_or_missing_evidence_cannot_shrink_a_weak_prefix(self):
        for word,evidence in ((w("bana",1_600_000,2_160_000),self.evidence()),(w("bana",820_000,2_160_000),[])):
            self.assertEqual(speech_pauses.refine_crossing_words([word],evidence),([word],[]))

    def test_different_occurrence_or_token_cannot_refine(self):
        original=w("bana",820_000,2_160_000)
        for short in ((3_780_000,4_160_000),(1_780_000,2_300_000)):
            self.assertEqual(speech_pauses.refine_crossing_words([original],self.evidence((short,))),([original],[]))
        self.assertEqual(speech_pauses.refine_crossing_words([w("hani",820_000,2_160_000)],self.evidence())[1],[])

    def test_competing_short_contexts_keep_earliest_prefix(self):
        word=w("bana",820_000,2_160_000)
        refined,_=speech_pauses.refine_crossing_words([word],self.evidence(((1_600_000,2_160_000),(1_780_000,2_160_000))))
        self.assertEqual(refined,[w("bana",1_600_000,2_160_000)])


class PauseRefinementIntegrationTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown

    def test_restored_weak_word_guard_allows_verified_pause_without_prefix_loss(self):
        work=self.root/"pause-refinement";work.mkdir()
        tool.write_json(work/"speech-long-word-rechecks.json",{"windows":[]})
        analysis={"audio_duration_us":2_000_000,"keep_ranges_us":[[0,2_000_000]],
                  "speech_ranges_us":[[0,500_000],[1_500_000,2_000_000]],"conservatively_protected_ranges_us":[]}
        def classify(records,*args):
            for i,record in enumerate(records):
                record["words"]=[w("bana",300_000,1_200_000)] if i==0 else [w("bana",1_000_000,1_200_000)]
            return [{"coverage":2}],[(600_000,980_000)],[]
        def sides(result,duration,offset):
            return ([w("harcamak",100_000,400_000)],[]) if offset==0 else ([w("inanılmaz",1_250_000,1_450_000)],[])
        with patch.object(speech_pauses,"detect",return_value=[]),patch.object(speech_pauses,"read_audio",return_value=[0]*32000), \
             patch.object(speech_pauses,"transcribe",return_value={"segments":[]}),patch.object(speech_pauses,"window_words",side_effect=sides), \
             patch.object(speech_pauses,"classify",side_effect=classify):
            result=speech_pauses.review(self.media,analysis,self.config,work)
        self.assertEqual(result["keep_ranges_us"],[[0,600_000],[980_000,2_000_000]])
        self.assertEqual(result["pause_review"]["independent_context_word_protection_us"],[(980_000,1_220_000)])
        audit=tool.read_json(work/"speech-pause-audit.json")
        self.assertEqual(audit["decisions"][0]["context_word_refinements"][0]["refined_word"],w("bana",1_000_000,1_200_000))
