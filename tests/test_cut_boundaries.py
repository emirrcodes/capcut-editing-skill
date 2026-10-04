"""Synthetic regressions for tiny intersections at existing clip boundaries."""
import copy
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from test_workflow import draft, project
import capcut_tool as tool
from draft_primitives import apply_timeline_keep_ranges, protect_cut_boundaries, validate_cut_fragments


class BoundaryTests(unittest.TestCase):
    setUp = fixtures.WorkflowTests.setUp
    tearDown = fixtures.WorkflowTests.tearDown

    def test_three_ms_intersection_refused_before_any_mutation(self):
        value = draft(self.media, (2_000_000, 2_000_000))
        before = copy.deepcopy(value)
        with self.assertRaisesRegex(RuntimeError, "3000 us"):
            apply_timeline_keep_ranges(value, [(0, 2_003_000)])
        self.assertEqual(value, before)

    def test_exactly_100_ms_is_allowed(self):
        value = draft(self.media, (2_000_000, 2_000_000))
        before = copy.deepcopy(value)
        apply_timeline_keep_ranges(value, [(0, 2_100_000)])
        validate_cut_fragments(value, before)
        self.assertEqual(value["tracks"][0]["segments"][-1]["target_timerange"]["duration"], 100_000)

    def test_existing_short_clip_is_kept_and_cannot_be_shortened(self):
        value = draft(self.media, (1_000_000, 30_000, 1_000_000))
        before = copy.deepcopy(value)
        apply_timeline_keep_ranges(value, [(0, value["duration"])])
        validate_cut_fragments(value, before)
        self.assertEqual(value, before)
        with self.assertRaisesRegex(RuntimeError, "micro-clip"):
            apply_timeline_keep_ranges(value, [(0, 1_010_000)])
        self.assertEqual(value, before)

    def test_final_validation_rejects_new_one_frame_clip(self):
        before = draft(self.media)
        value = copy.deepcopy(before)
        segment = value["tracks"][0]["segments"][-1]
        segment["source_timerange"]["duration"] = 33_333
        segment["target_timerange"]["duration"] = 33_333
        value["duration"] = 1_033_333
        tool.validate(value)
        with self.assertRaisesRegex(RuntimeError, "New or shortened"):
            validate_cut_fragments(value, before)

    def test_safe_protection_keeps_all_requested_audio_without_bridging_source_gaps(self):
        value = draft(self.media, (2_000_000, 2_000_000))
        value["tracks"][0]["segments"][1]["source_timerange"]["start"] = 10_000_000
        before = copy.deepcopy(value)
        keep, extra = protect_cut_boundaries(value, [(0, 2_003_000)])
        self.assertEqual(keep, [(0, 2_100_000)])
        self.assertEqual(extra, [[2_003_000, 2_100_000]])
        apply_timeline_keep_ranges(value, keep)
        validate_cut_fragments(value, before)
        self.assertEqual([s["source_timerange"] for s in value["tracks"][0]["segments"]],
                         [{"start": 0, "duration": 2_000_000}, {"start": 10_000_000, "duration": 100_000}])

    def test_existing_short_clip_is_protected_even_outside_the_keep_plan(self):
        value = draft(self.media, (1_000_000, 30_000, 1_000_000))
        keep, extra = protect_cut_boundaries(value, [(0, 500_000), (1_530_000, 2_030_000)])
        self.assertIn((1_000_000, 1_030_000), keep)
        self.assertEqual(extra, [[1_000_000, 1_030_000]])
        before = copy.deepcopy(value)
        apply_timeline_keep_ranges(value, keep)
        validate_cut_fragments(value, before)

    def test_post_write_validation_failure_rolls_back_every_copy(self):
        folder = project(self.root, draft(self.media))
        paths = tool.source_paths(folder)
        before = {p: p.read_bytes() for p in paths}
        update = draft(self.media)
        update["name"] = "proposed change"
        payloads = {p: tool.encoded(update) if p.name != "draft_meta_info.json" else before[p] for p in paths}
        with patch.object(tool, "is_capcut_running", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "original files restored"):
                tool.commit(folder, payloads, tool.snapshot(folder, paths), "edit",
                            verify_written=lambda: (_ for _ in ()).throw(RuntimeError("invalid output fragments")))
        self.assertEqual(before, {p: p.read_bytes() for p in paths})


if __name__ == "__main__":
    unittest.main()
