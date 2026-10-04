import copy,json,unittest
from unittest.mock import patch
import test_workflow as fixtures
from test_workflow import draft,project,transcript
import capcut_tool as tool


class TranscriptReviewTests(unittest.TestCase):
    setUp=fixtures.WorkflowTests.setUp
    tearDown=fixtures.WorkflowTests.tearDown

    def staged(self):
        folder=project(self.root,draft(self.media));work=self.root/"review-caption"
        with patch("transcribe.transcribe",return_value=transcript(crossing=False)):
            tool.prepare(folder,"subtitles",work,self.config)
        source=tool.read_json(work/"transcript.json")
        revised=copy.deepcopy(source);revised["segments"][0]["words"][4]["start"]=1.08
        request={"transcript_sha256":tool.read_json(work/"words.json")["transcript_sha256"],
                 "audio_ranges_us":[[1000000,2000000]],"transcript":revised,"note":"Independent current clip word timing"}
        path=self.root/"review.json";tool.write_json(path,request)
        return folder,work,path,request

    def test_review_retains_original_and_evidence_without_project_writes(self):
        folder,work,path,request=self.staged();before=tool.snapshot(folder,tool.source_paths(folder));original=(work/"transcript.json").read_bytes()
        report=tool.review_transcript(work,path)
        self.assertFalse(report["writes_project"])
        self.assertEqual(tool.snapshot(folder,tool.source_paths(folder)),before)
        archives=list(work.glob("transcript-before-review-*.json"));self.assertEqual(len(archives),1)
        self.assertEqual(archives[0].read_bytes(),original)
        self.assertEqual(tool.read_json(work/"plan.json")["transcript_sha256"],tool.read_json(work/"words.json")["transcript_sha256"])
        tool.cleanup(work)
        self.assertTrue(archives[0].exists())
        self.assertEqual(len(list(work.glob("transcript-review-*.json"))),1)

    def test_stale_review_refused_before_staging(self):
        _,work,path,request=self.staged();original=(work/"transcript.json").read_bytes()
        request["transcript_sha256"]="0"*64;tool.write_json(path,request)
        with self.assertRaisesRegex(RuntimeError,"stale"):tool.review_transcript(work,path)
        self.assertEqual((work/"transcript.json").read_bytes(),original)
        self.assertEqual(list(work.glob("transcript-before-review-*.json")),[])

    def test_changes_outside_audio_review_ranges_refused(self):
        _,work,path,request=self.staged();request["transcript"]["segments"][0]["words"][0]["word"]="invented"
        tool.write_json(path,request)
        with self.assertRaisesRegex(RuntimeError,"outside"):tool.review_transcript(work,path)
        self.assertEqual(list(work.glob("transcript-before-review-*.json")),[])

    def test_nonmonotonic_revised_words_refused(self):
        _,work,path,request=self.staged();request["transcript"]["segments"][0]["words"][5]["start"]=1.0
        tool.write_json(path,request)
        with self.assertRaisesRegex(RuntimeError,"nonmonotonic"):tool.review_transcript(work,path)

    def test_source_changes_refuse_review(self):
        folder,work,path,_=self.staged();value=tool.read_json(folder/"draft_meta_info.json");value["changed"]=True
        tool.write_json(folder/"draft_meta_info.json",value)
        with self.assertRaisesRegex(RuntimeError,"project changed"):tool.review_transcript(work,path)
