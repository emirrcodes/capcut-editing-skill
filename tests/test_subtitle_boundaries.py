"""Regressions for gapless captions with incorrect ownership at video cuts."""
import copy
import unittest
from unittest.mock import patch
import test_workflow as fixtures
from test_workflow import draft,project,transcript
import capcut_tool as tool
from subtitle_boundaries import boundary_plan,validate_boundaries


def blocks(left_end=.75,right_start=1.1,right_end=1.3):
    return [[{"word":"sol","start":.1,"end":left_end}],
            [{"word":"sağ","start":right_start,"end":right_end}]]


class BoundaryTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown
    spec=fixtures.WorkflowTests.spec

    def test_late_right_word_starts_at_cut(self):
        plan=boundary_plan(blocks(),draft(self.media))
        self.assertEqual(plan["starts_us"],[0,1000000])
        self.assertEqual(plan["boundary_adjustments"][0]["reason"],"cut-in-speech-gap")

    def test_original_report_late_word_three_frame_carryover(self):
        value=draft(self.media,(8133333,2000000))
        source=blocks(8.02,8.22,8.5)
        self.assertEqual(boundary_plan(source,value)["starts_us"],[0,8133333])

    def test_early_crossing_right_word_rule_remains(self):
        self.assertEqual(boundary_plan(blocks(.75,.90,1.2),draft(self.media))["starts_us"],[0,1000000])

    def test_word_finishing_before_cut_stays_left(self):
        self.assertEqual(boundary_plan(blocks(.75,.90,.95),draft(self.media))["starts_us"],[0,900000])

    def test_left_speech_crossing_cut_keeps_natural_phrase_start(self):
        self.assertEqual(boundary_plan(blocks(1.1,1.2,1.4),draft(self.media))["starts_us"],[0,1200000])

    def test_same_clip_gap_keeps_natural_start(self):
        self.assertEqual(boundary_plan(blocks(.3,.5,.7),draft(self.media))["starts_us"],[0,500000])

    def test_single_cut_long_gap_not_limited_to_250ms(self):
        self.assertEqual(boundary_plan(blocks(.4,1.6,1.8),draft(self.media))["starts_us"],[0,1000000])

    def test_multiple_cuts_require_current_clip_audio_review(self):
        value=draft(self.media,(800000,200000,1000000))
        with self.assertRaisesRegex(RuntimeError,"multiple cuts"):
            boundary_plan(blocks(.4,1.6,1.8),value)

    def test_alignment_collision_requests_semantic_regrouping(self):
        source=[[{"word":"ilk","start":0,"end":.7}],
                [{"word":"orta","start":.9,"end":1.05}],
                [{"word":"son","start":.95,"end":1.2}]]
        value=draft(self.media)
        with self.assertRaisesRegex(RuntimeError,"collide"):
            boundary_plan(source,value)

    def late_fixture(self):
        source=transcript(crossing=False)
        result=tool.insert_subtitles(draft(self.media),source,{"ranges":[[1,4],[5,8]]},self.config)
        return source,result

    def test_gapless_wrong_output_rejected_with_fresh_words(self):
        source,result=self.late_fixture();segments=result["tracks"][-1]["segments"]
        segments[0]["target_timerange"]["duration"]=1100000
        segments[1]["target_timerange"]={"start":1100000,"duration":900000}
        raw=tool.subtitle_blocks(source,{"ranges":[[1,4],[5,8]]},self.config,2000000)
        with self.assertRaisesRegex(RuntimeError,"clip ownership"):
            validate_boundaries(result,raw)

    def test_saved_payloads_catch_three_frame_carryover(self):
        _,result=self.late_fixture();result["fps"]=30;segments=result["tracks"][-1]["segments"]
        segments[0]["target_timerange"]["duration"]=1100000
        segments[1]["target_timerange"]={"start":1100000,"duration":900000}
        with self.assertRaisesRegex(RuntimeError,"clip ownership"):
            validate_boundaries(result)

    def test_saved_one_frame_uncertainty_is_reported_and_raw_is_strict(self):
        source,result=self.late_fixture();result["fps"]=30;segments=result["tracks"][-1]["segments"]
        segments[0]["target_timerange"]["duration"]=1033333
        segments[1]["target_timerange"]={"start":1033333,"duration":966667}
        report=validate_boundaries(result)
        self.assertTrue(report["boundary_uncertainties"])
        raw=tool.subtitle_blocks(source,{"ranges":[[1,4],[5,8]]},self.config,2000000)
        with self.assertRaisesRegex(RuntimeError,"clip ownership"):
            validate_boundaries(result,raw)

    def test_apply_checks_saved_boundaries_and_preserves_video(self):
        value=draft(self.media);folder=project(self.root,value);work=self.root/"caption-boundary"
        with patch("transcribe.transcribe",return_value=transcript(crossing=False)):
            tool.prepare(folder,"subtitles",work,self.config)
        tool.write_json(work/"subtitles.json",self.spec(work))
        with patch.object(tool,"is_capcut_running",return_value=False):report=tool.apply(work)
        saved=tool.read_json(folder/"draft_info.json")
        self.assertEqual(saved["tracks"][0],value["tracks"][0])
        self.assertEqual(saved["duration"],value["duration"])
        self.assertEqual(report["subtitle_blocks"],2)
        self.assertEqual(report["boundary_validation_basis"],"fresh-raw-words")
        self.assertEqual(len({p.read_bytes() for p in tool.draft_paths(folder)}),1)
        self.assertTrue((folder/("draft_info.json"+report["backup_suffix"])).is_file())

    def test_audio_only_cut_ownership_is_supported(self):
        value=draft(self.media,audio_only=True)
        self.assertEqual(boundary_plan(blocks(),value)["starts_us"],[0,1000000])

    def test_real_cli_preview_uses_current_raw_words(self):
        import subprocess,sys,json
        folder=project(self.root,draft(self.media));work=self.root/"preview-boundary"
        with patch("transcribe.transcribe",return_value=transcript(crossing=False)):
            tool.prepare(folder,"subtitles",work,self.config)
        tool.write_json(work/"subtitles.json",self.spec(work))
        result=subprocess.run([sys.executable,str(tool.HERE/"capcut_tool.py"),"preview",str(work)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)["boundary_validation_basis"],"fresh-raw-words")

    def test_mtime_only_write_during_stability_check_is_rejected(self):
        import os
        folder=project(self.root,draft(self.media));paths=tool.source_paths(folder)
        expected=tool.snapshot(folder,paths);payloads={path:path.read_bytes() for path in paths}
        target=folder/"draft_info.json";stat=target.stat()
        def touched(_):os.utime(target,ns=(stat.st_atime_ns,stat.st_mtime_ns+1))
        with patch.object(tool,"is_capcut_running",return_value=False),patch.object(tool.time,"sleep",side_effect=touched):
            with self.assertRaisesRegex(RuntimeError,"mtime/size"):
                tool.commit(folder,payloads,expected,"subtitles")
        self.assertEqual(list(folder.glob("*.bak")),[])
