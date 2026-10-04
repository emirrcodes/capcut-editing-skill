"""Two-way caption ownership at media cuts, independent of gapless coverage."""
from __future__ import annotations
import math


def frame_uncertainty(draft):
    value = draft.get("fps")
    if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
        return 0
    return min(50_000, math.ceil(1_000_000/value))


def boundary_plan(blocks, draft, *, word_uncertainty_us=0):
    from capcut_tool import primary_track
    cuts = [s["target_timerange"]["start"] for s in primary_track(draft)["segments"][1:]]
    if not blocks or any(not block for block in blocks):
        raise RuntimeError("Subtitle boundary plan requires nonempty word blocks")
    starts, adjustments = [0], []
    for index in range(1,len(blocks)):
        first=blocks[index][0]
        natural=round(first["start"]*1e6); end=round(first["end"]*1e6)
        left_end=max(round(w["end"]*1e6) for w in blocks[index-1])
        gap_cuts=[cut for cut in cuts if left_end-word_uncertainty_us <= cut <= natural]
        early_cuts=[cut for cut in cuts if 0 < cut-natural <= 250_000
                    and end+word_uncertainty_us > cut and left_end-word_uncertainty_us <= cut]
        candidates=sorted(set(gap_cuts+early_cuts))
        if len(candidates)>1:
            raise RuntimeError(f"Ambiguous subtitle boundary before block {index+1}: multiple cuts {candidates}. Inspect current clip audio and refine word times or semantic grouping; do not choose by proximity.")
        start=candidates[0] if candidates else natural
        if start != natural:
            adjustments.append({"right_block":index+1,"natural_start_us":natural,"planned_start_us":start,
                                "left_speech_end_us":left_end,"right_word_end_us":end,
                                "reason":"cut-in-speech-gap" if start in gap_cuts else "early-right-word"})
        starts.append(start)
    if any(right<=left for left,right in zip(starts,starts[1:])) or starts[-1]>=draft["duration"]:
        raise RuntimeError("Subtitle starts collide after cut alignment; revise semantic phrase blocks")
    return {"starts_us":starts,"boundary_adjustments":adjustments}


def saved_blocks(draft):
    track=next(t for t in draft["tracks"] if t.get("type")=="text" and t.get("name")=="codex_subtitles")
    materials={m["id"]:m for m in draft["materials"]["texts"]}
    blocks=[]
    for segment in track["segments"]:
        origin=segment["target_timerange"]["start"]; payload=materials[segment["material_id"]]["words"]
        words=[{"word":text,"start":(origin+start*1000)/1e6,"end":(origin+end*1000)/1e6}
               for text,start,end in zip(payload["text"],payload["start_time"],payload["end_time"]) if str(text).strip()]
        if not words: raise RuntimeError("Saved subtitle has no reconstructable word times")
        blocks.append(words)
    return blocks


def validate_boundaries(draft, source_blocks=None):
    track=next(t for t in draft["tracks"] if t.get("type")=="text" and t.get("name")=="codex_subtitles")
    tolerance=0 if source_blocks is not None else frame_uncertainty(draft)
    blocks=source_blocks if source_blocks is not None else saved_blocks(draft)
    if len(blocks)!=len(track["segments"]):raise RuntimeError("Subtitle/source block counts disagree")
    plan=boundary_plan(blocks,draft,word_uncertainty_us=tolerance)
    uncertainties=[]
    for index,(segment,expected) in enumerate(zip(track["segments"],plan["starts_us"])):
        actual=segment["target_timerange"]["start"]
        if abs(actual-expected)>tolerance:
            raise RuntimeError(f"Subtitle block {index+1} violates clip ownership: starts at {actual}, expected {expected} us")
        if actual!=expected:
            uncertainties.append({"block":index+1,"actual_start_us":actual,"expected_start_us":expected,"difference_us":actual-expected})
    return {"boundary_adjustments":plan["boundary_adjustments"],"boundary_uncertainties":uncertainties,
            "boundary_validation_basis":"fresh-raw-words" if source_blocks is not None else "saved-relative-words",
            "word_timestamp_uncertainty_us":tolerance}
