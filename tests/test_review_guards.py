"""Independent evidence gates: source prefixes, repeated words, clip ownership."""
import copy
from pathlib import Path
import unittest
from unittest.mock import patch
import test_workflow as fixtures
from test_workflow import draft, project, transcript
import capcut_tool as tool
import caption_review
import speech_pauses
import speech_verify
from subtitle_boundaries import boundary_plan
from test_subtitle_boundaries import blocks
from draft_primitives import apply_timeline_keep_ranges


def observation(context, left, right, word="bana", suspects=()):
    return {"range_us":context,"words":[{"word":word,"start_us":left,"end_us":right}],"suspect_ranges_us":list(suspects)}


class ContextGuardTests(unittest.TestCase):
    def observations(self):
        return [observation([0,8_000_000],3_600_000,4_160_000),
                observation([2_000_000,10_000_000],2_820_000,4_160_000)]

    def test_shorter_corroborated_weak_interval_protects_prefix_not_stretched_pause(self):
        guards,evidence=speech_pauses.context_word_guards(self.observations(),[(4_066_666,4_300_000)],10_000_000)
        self.assertEqual(guards,[(3_580_000,4_180_000)])
        self.assertEqual(evidence[0]["vad_overlap_us"],93_334)
        self.assertEqual(len(evidence[0]["corroborating_contexts"]),1)

    def test_duplicate_context_or_other_occurrence_cannot_corroborate(self):
        records=self.observations()
        for other in (records[0],observation([2_000_000,10_000_000],5_000_000,5_400_000)):
            self.assertEqual(speech_pauses.context_word_guards([records[0],other],[],10_000_000)[0],[])

    def test_cropped_or_suspect_word_is_not_a_prefix_anchor(self):
        records=self.observations()
        for other in (observation([3_600_000,10_000_000],3_600_000,4_160_000),
                      observation([2_000_000,10_000_000],2_820_000,4_160_000,suspects=[(3_800_000,4_000_000)])):
            self.assertEqual(speech_pauses.context_word_guards([records[0],other],[],10_000_000)[0],[])

    def test_two_stretched_words_do_not_restore_a_long_pause(self):
        records=[observation([0,8_000_000],2_820_000,4_160_000),observation([2_000_000,10_000_000],2_820_000,4_160_000)]
        self.assertEqual(speech_pauses.context_word_guards(records,[],10_000_000)[0],[])

    def test_vad_supported_word_does_not_add_extra_guard(self):
        self.assertEqual(speech_pauses.context_word_guards(self.observations(),[(3_600_000,4_160_000)],10_000_000)[0],[])


class CaptionGuardTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown
    spec=fixtures.WorkflowTests.spec

    def test_253ms_and_300ms_crossings_require_review_instead_of_silent_early_caption(self):
        value=draft(self.media)
        for start in (.746667,.70):
            with self.assertRaisesRegex(RuntimeError,"250 ms"):
                boundary_plan(blocks(.6,start,1.1),value)
        self.assertEqual(boundary_plan(blocks(.6,.75,1.1),value)["starts_us"],[0,1_000_000])

    def test_left_speech_continuing_across_cut_keeps_natural_grouping(self):
        self.assertEqual(boundary_plan(blocks(1.1,.7,1.3),draft(self.media))["starts_us"],[0,700_000])

    def stretched(self):
        source={"segments":[{"start":.1,"end":1.9,"words":[{"word":"bu","start":.1,"end":1.84},
                                                                  {"word":"son","start":1.85,"end":1.9}]}]}
        value=draft(self.media,(500_000,500_000,1_000_000))
        return value,source

    def staged_stretch(self):
        value,source=self.stretched();folder=project(self.root,value);work=self.root/"caption-guard"
        with patch("transcribe.transcribe",return_value=source),patch.object(caption_review,"transcribe",return_value=source):
            report=tool.prepare(folder,"subtitles",work,self.config)
        return folder,work,source,report

    def test_stretched_multi_cut_word_is_rejected_before_project_write(self):
        folder,work,source,report=self.staged_stretch()
        tool.write_json(work/"subtitles.json",{"transcript_sha256":tool.read_json(work/"plan.json")["transcript_sha256"],"ranges":[[1,2]]})
        before=tool.snapshot(folder,tool.source_paths(folder))
        with self.assertRaisesRegex(RuntimeError,"Caption audio review"):
            tool.apply(work,project_closed=True)
        self.assertEqual(tool.snapshot(folder,tool.source_paths(folder)),before)
        self.assertEqual(list(folder.glob("*.bak")),[])
        evidence=tool.read_json(work/"caption-audio-review.json")
        self.assertEqual(evidence["issues"][0]["reasons"],["stretched-word","multiple-clip-cuts"])
        self.assertGreaterEqual(len(evidence["independent_audio_reviews"]),4)
        self.assertTrue(all((work/record["audio_file"]).exists() for record in evidence["independent_audio_reviews"]))
        self.assertEqual(report["caption_audio_review"]["issue_count"],1)

    def request(self,work,source,evidence=False):
        plan=tool.read_json(work/"plan.json")
        request={"transcript_sha256":plan["transcript_sha256"],"audio_ranges_us":[[0,2_000_000]],"transcript":source,
                 "note":"Independent bounded current clips confirm the acoustic words, including repetitions"}
        if evidence:request["audio_review_sha256"]=plan["caption_audio_review"]["sha256"]
        path=self.root/"resolution.json";tool.write_json(path,request);return path

    def test_note_alone_cannot_clear_unchanged_stretched_word(self):
        _,work,source,_=self.staged_stretch()
        tool.review_transcript(work,self.request(work,source))
        plan=tool.read_json(work/"plan.json")
        tool.write_json(work/"subtitles.json",{"transcript_sha256":plan["transcript_sha256"],"ranges":[[1,2]]})
        with self.assertRaisesRegex(RuntimeError,"Caption audio review"):tool.build_result(work,None)

    def test_hash_bound_audio_review_allows_a_confirmed_slow_word(self):
        _,work,source,_=self.staged_stretch()
        tool.review_transcript(work,self.request(work,source,True))
        plan=tool.read_json(work/"plan.json")
        tool.write_json(work/"subtitles.json",{"transcript_sha256":plan["transcript_sha256"],"ranges":[[1,2]]})
        self.assertEqual(tool.validate_subtitles(tool.build_result(work,None)[0],self.config)["subtitle_blocks"],1)
        self.assertEqual(plan["caption_verified_ranges_us"],[[100_000,1_840_000]])

    def test_changed_independent_audio_is_rejected_before_staging(self):
        _,work,source,_=self.staged_stretch();path=self.request(work,source,True)
        record=tool.read_json(work/"caption-audio-review.json")["independent_audio_reviews"][0]
        (work/record["audio_file"]).write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError,"audio changed"):tool.review_transcript(work,path)
        self.assertEqual(list(work.glob("transcript-before-review-*.json")),[])

    def test_supported_correction_restores_repeats_and_rebuilds_indexes(self):
        _,work,source,_=self.staged_stretch()
        revised={"segments":[{"start":.1,"end":1.9,"words":[{"word":"bu","start":.1,"end":.3},
                   {"word":"bu","start":.55,"end":.7},{"word":"bu","start":1.1,"end":1.3},
                   {"word":"son","start":1.85,"end":1.9}]}]}
        tool.review_transcript(work,self.request(work,revised))
        words=tool.read_json(work/"words.json")
        self.assertEqual([w["word"] for w in words["words"]],["bu","bu","bu","son"])
        tool.write_json(work/"subtitles.json",{"transcript_sha256":words["transcript_sha256"],"ranges":[[1,4]]})
        self.assertEqual(tool.validate_subtitles(tool.build_result(work,None)[0],self.config)["subtitle_blocks"],1)

    def test_regular_captions_do_not_run_extra_audio_review(self):
        value=draft(self.media);work=self.root/"unused";work.mkdir()
        with patch.object(caption_review,"transcribe") as transcriber:
            self.assertIsNone(caption_review.audit(work,value,transcript(),self.config,"0"*64))
        transcriber.assert_not_called()

    def test_native_subframe_payload_overflow_reported_saved_but_rejected_raw(self):
        source=transcript(False);value=tool.insert_subtitles(draft(self.media),source,{"ranges":[[1,4],[5,8]]},self.config)
        value["fps"]=30
        for field in ("words","current_words"):value["materials"]["texts"][-1][field]["end_time"][-1]=1007
        report=tool.validate_subtitles(value,self.config)
        self.assertEqual(len(report["word_timing_uncertainties"]),2)
        raw=tool.subtitle_blocks(source,{"ranges":[[1,4],[5,8]]},self.config,2_000_000)
        with self.assertRaisesRegex(RuntimeError,"outside"):tool.validate_subtitles(value,self.config,raw)
        value["materials"]["texts"][-1]["words"]["end_time"][-1]=1034
        with self.assertRaisesRegex(RuntimeError,"outside"):tool.validate_subtitles(value,self.config)

    def test_diagnostic_destination_failure_stops_before_backup_and_project_write(self):
        folder=project(self.root,draft(self.media));work=self.root/"diagnostics-failure"
        with patch("transcribe.transcribe",return_value=transcript(False)):tool.prepare(folder,"subtitles",work,self.config)
        tool.write_json(work/"subtitles.json",self.spec(work))
        (self.root/"diagnostics-failure-diagnostics-existing.json").write_text("keep")
        before=tool.snapshot(folder,tool.source_paths(folder))
        prepared_result=tool.build_result(work,None)
        with patch.object(tool,"build_result",return_value=prepared_result),patch.object(tool,"fresh_id",return_value="existing"):
            with self.assertRaises(FileExistsError):tool.apply(work,project_closed=True)
        self.assertEqual(tool.snapshot(folder,tool.source_paths(folder)),before)
        self.assertEqual(list(folder.glob("*.bak")),[])

    def test_successful_apply_leaves_diagnostics_after_work_cleanup(self):
        folder=project(self.root,draft(self.media));work=self.root/"diagnostics"
        with patch("transcribe.transcribe",return_value=transcript(False)):tool.prepare(folder,"subtitles",work,self.config)
        tool.write_json(work/"subtitles.json",self.spec(work))
        report=tool.apply(work,project_closed=True)
        archive=tool.read_json(Path(report["diagnostics_archive"]))
        self.assertEqual(archive["settings"],self.config)
        self.assertIn("transcript.json",archive["evidence"])
        self.assertTrue(archive["source_snapshot"])
        self.assertFalse(work.exists())


class SourcePrefixTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown

    def test_same_recognized_token_does_not_hide_lost_independent_prefix(self):
        original=draft(self.media,(2_000_000,));keep=[(1_066_666,1_300_000)]
        candidate=copy.deepcopy(original);apply_timeline_keep_ranges(candidate,keep)
        analysis={"keep_ranges_us":keep,"speech_ranges_us":[],"conservatively_protected_ranges_us":[],
                  "pause_review":{"independent_context_word_protection_us":[[600_000,1_160_000]]}}
        words={"segments":[{"words":[{"word":"bana","start":.6,"end":1.16}]}]}
        report=speech_verify.compare(words,words,original,self.root,analysis)
        self.assertEqual(report["changed_or_missing_words"],[])
        self.assertEqual(report["unexpected_independent_word_source_loss_us"],466_666)
        work=self.root/"prefix-verify";work.mkdir();tool.write_json(work/"speech-word-transcript.json",words)
        with patch.object(speech_verify,"transcribe",return_value=words):
            with self.assertRaisesRegex(RuntimeError,"independently protected"):
                speech_verify.verify(original,candidate,self.root,analysis,self.media,self.config,work)
