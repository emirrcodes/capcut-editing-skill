"""Whole-timeline contextual review of pauses hidden by approximate word times."""
from __future__ import annotations
from difflib import SequenceMatcher
from pathlib import Path
import re

from draft_primitives import turkish_lower
from speech_scan import detect, gaps, merge, read_audio
from speech_words import extract_window, trusted_words, word_protection
from transcribe import transcribe


def token(word):
    return re.sub(r"[^\w]+", "", turkish_lower(str(word)))


def window_words(result, duration, offset):
    # A malformed word affects its segment, not every unrelated phrase in a
    # long context. Keep that segment uncertain; do not trust zero-length words.
    words, suspects = [], []
    for segment in result.get("segments", []):
        if segment.get("avg_logprob", 0) < -1:
            left = max(0,offset+round(segment.get("start",0)*1e6))
            right = min(duration,offset+round(segment.get("end",0)*1e6))
            if right > left: suspects.append((left,right))
            continue
        try:
            found, uncertain = trusted_words({"segments": [segment]}, duration, offset)
            words.extend(found); suspects.extend(uncertain)
        except (RuntimeError, KeyError, TypeError, ValueError):
            left = max(0, offset + round(segment.get("start", 0) * 1e6))
            right = min(duration, offset + round(segment.get("end", 0) * 1e6))
            suspects.append((left, max(left + 1, right)))
    return words, merge(suspects, duration)


def classify(records, duration, minimum):
    events = {0, duration}
    for record in records:
        events.update(record["core_us"])
        for key in ("voice_keep_us", "word_protection_us", "suspect_ranges_us"):
            for left, right in record[key]:
                events.update((max(0, left), min(duration, right)))
    events = sorted(events); parts = []
    for left, right in zip(events, events[1:]):
        point = (left + right) // 2
        active = [r for r in records if r["core_us"][0] <= point < r["core_us"][1]]
        votes = {key: sum(any(a <= point < b for a, b in r[key]) for r in active)
                 for key in ("voice_keep_us", "word_protection_us", "suspect_ranges_us")}
        parts.append({"range_us": [left, right], "coverage": len(active), **votes})
    candidates = merge([tuple(p["range_us"]) for p in parts if p["coverage"] >= 2
                        and not p["voice_keep_us"] and not p["suspect_ranges_us"]], duration)
    candidates = [span for span in candidates if span[1] - span[0] >= minimum]
    voice_only = merge([tuple(p["range_us"]) for p in parts if p["coverage"] >= 2
                        and p["voice_keep_us"] and not p["word_protection_us"] and not p["suspect_ranges_us"]], duration)
    return parts, candidates, [span for span in voice_only if span[1]-span[0] >= minimum]


def anchored(crossing, prefix, suffix):
    # Recognize the whole boundary word on one side. Never shorten an interval
    # merely because its token vanished. Same token on both sides can represent
    # a split syllable or a repetition; leave that ambiguous boundary intact.
    if not prefix or not suffix:
        return False, "missing-side-anchor"
    left, right = token(prefix[-1]["word"]), token(suffix[0]["word"])
    if left == right:
        return False, "same-boundary-token-kept"
    before = [token(w["word"]) for w in prefix[-2:]]
    after = [token(w["word"]) for w in suffix[:2]]
    for word in crossing:
        normalized = token(word["word"])
        first = any(SequenceMatcher(None, normalized, item, autojunk=False).ratio() >= .85 for item in before)
        last = any(SequenceMatcher(None, normalized, item, autojunk=False).ratio() >= .85 for item in after)
        if first == last:
            return False, "crossing-word-unresolved"
    return True, "independent-word-anchors"



def retained_declines(decisions, keep, duration):
    return merge([(max(left,a),min(right,b))
                  for record in decisions if record["status"] != "remove"
                  for left,right in [record["range_us"]] for a,b in keep],duration)


def short_word_guards(rechecks, duration):
    # VAD can miss the weak beginning of a real short word. A suffix cropped
    # into that word may still decode the complete token; that is not proof its
    # full acoustic start lies after the crop. Keep short words independently
    # recovered in uncropped local refinement windows, including their edges.
    return merge([(word["start_us"]-20_000,word["end_us"]+20_000)
                  for record in rechecks if not record.get("suspect_ranges_us")
                  for word in record.get("recovered_words",[])
                  if 0 < word["end_us"]-word["start_us"] <= 500_000],duration)


def review(audio: Path, analysis: dict, config: dict, work: Path) -> dict:
    from capcut_tool import write_json, read_json
    duration = analysis["audio_duration_us"]; minimum = round(config["speech_min_gap"] * 1e6)
    starts = list(range(0, max(1, duration - 8_000_000 + 1), 3_000_000))
    starts.append(max(0, duration - 8_000_000))
    spans = sorted(set([(s, min(duration, s+8_000_000)) for s in starts] +
                       [(0, min(duration, 5_500_000)), (max(0, duration-5_500_000), duration)]))
    if duration < 5_500_000 and duration > 200_000:
        spans = sorted(set([*spans, (0,duration-100_000), (100_000,duration)]))
    temporary = work / "speech-pause-review.wav"; records, decisions, confirmed = [], [], []
    try:
        for left, right in spans:
            extract_window(audio, temporary, left, right)
            samples = read_audio(temporary)
            raw = merge([*detect(samples, config["speech_threshold"], config),
                         *detect(samples, config["speech_review_threshold"], config)], len(samples))
            speech = [(left+round(a/16000*1e6), min(duration,left+round(b/16000*1e6))) for a,b in raw]
            result = transcribe(temporary, config, speech_review=True)
            words, suspects = window_words(result, duration, left)
            padding = round(config["speech_padding"] * 1e6)
            records.append({"range_us": [left,right],
                            "core_us": [left if left==0 else left+min(400_000,(right-left)//10), right if right==duration else right-min(400_000,(right-left)//10)],
                            "speech_ranges_us": speech,
                            "voice_keep_us": merge([(a-padding,b+padding) for a,b in speech],duration),
                            "word_protection_us": word_protection(words,speech,duration),
                            "words": words, "suspect_ranges_us": suspects, "transcript": result})
        parts, candidates, voice_only = classify(records, duration, minimum)
        # Final verification retains ALL raw global VAD-supported source audio.
        # Local consensus can refine word protection; it cannot bypass that guard.
        global_speech = merge([tuple(span) for key in ("speech_ranges_us", "conservatively_protected_ranges_us")
                               for span in analysis[key]], duration)
        refinements = read_json(work/"speech-long-word-rechecks.json")["windows"]
        short_guards = short_word_guards(refinements,duration)
        global_allowed = gaps(merge([*global_speech,*short_guards],duration),duration)
        for left, right in candidates:
            allowed = merge([(max(left,a),min(right,b)) for a,b in global_allowed],duration)
            for a,b in allowed:
                if b-a < minimum:
                    continue
                crossing = []
                for record in records:
                    if record["core_us"][0] <= a and record["core_us"][1] >= b:
                        crossing.extend(w for w in record["words"] if w["end_us"] > a and w["start_us"] < b)
                sides = []; side_records = []
                for label,first,last in (("prefix",max(0,a-2_500_000),a), ("suffix",b,min(duration,b+2_500_000))):
                    if last-first < 100_000:
                        result,words,suspects = {"segments":[]},[],[]
                    else:
                        extract_window(audio,temporary,first,last)
                        result = transcribe(temporary,config,speech_review=True)
                        words,suspects = window_words(result,duration,first)
                        if suspects or not words:
                            first = max(0,a-3_500_000) if label=="prefix" else first
                            last = min(duration,b+3_500_000) if label=="suffix" else last
                            extract_window(audio,temporary,first,last)
                            result = transcribe(temporary,config,speech_review=True)
                            words,suspects = window_words(result,duration,first)
                    sides.append((words,suspects))
                    side_records.append({"side":label,"range_us":[first,last],"words":words,
                                         "suspect_ranges_us":suspects,"transcript":result})
                accepted, reason = anchored(crossing,sides[0][0],sides[1][0])
                if any(a <= word["start_us"] and word["end_us"] <= b for word in crossing):
                    accepted,reason = False,"weak-word-inside-gap-kept"
                if sides[0][1] or sides[1][1]:
                    accepted,reason = False,"suspect-side-kept"
                if accepted: confirmed.append((a,b))
                decisions.append({"range_us":[a,b],"status":"remove" if accepted else "no-additional-cut",
                                  "reason":reason,"crossing_words":crossing,"side_reviews":side_records})
        report = {"method":"overlapping-context-vad-and-word-anchors", "duration_us":duration,
                  "window_count":len(records),"minimum_independent_coverage":min(p["coverage"] for p in parts),
                  "confirmed_non_speech_ranges_us":confirmed,"decisions":decisions,
                  "vad_only_kept_ranges_us":voice_only,"independent_short_word_protection_us":short_guards,"records":records,"coverage":parts,
                  "note":"All timeline regions are scanned in overlapping contexts. Suspect, missing, and ambiguous anchors stay. VAD-supported source audio is never overridden."}
        write_json(work/"speech-pause-audit.json",report)
        keep = merge([*(tuple(span) for span in analysis["keep_ranges_us"]),*short_guards],duration)
        allowed = gaps(confirmed,duration)
        keep = merge([(max(a,left),min(b,right)) for a,b in keep for left,right in allowed],duration)
        if not keep: raise RuntimeError("Pause review would remove the whole timeline")
        output = dict(analysis)
        output.update({"method":"silero-vad-word-and-whole-timeline-pause-review",
                       "keep_ranges_us":[list(span) for span in keep],
                       "pause_review":{"window_count":len(records),"minimum_independent_coverage":report["minimum_independent_coverage"],
                                       "confirmed_non_speech_ranges_us":confirmed,
                                       "context_review_declined_ranges_us":[r["range_us"] for r in decisions if r["status"] != "remove"],
                                       "kept_uncertain_ranges_us":[list(span) for span in retained_declines(decisions,keep,duration)],
                                       "vad_only_kept_ranges_us":voice_only,"independent_short_word_protection_us":short_guards}})
        return output
    finally:
        temporary.unlink(missing_ok=True)
