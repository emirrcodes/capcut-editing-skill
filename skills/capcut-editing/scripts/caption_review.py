"""Require bounded independent audio evidence for stretched caption word times."""
from __future__ import annotations
import hashlib
from pathlib import Path
from speech_words import extract_window
from transcribe import transcribe


def flags(words, draft, verified_ranges=()):
    from capcut_tool import primary_track
    cuts=[s["target_timerange"]["start"] for s in primary_track(draft)["segments"][1:]]
    issues=[]
    for index,word in enumerate(words,1):
        left,right=round(word["start"]*1e6),round(word["end"]*1e6)
        crossed=[cut for cut in cuts if left < cut < right]
        reasons=[]
        if right-left>1_500_000: reasons.append("stretched-word")
        if len(crossed)>1: reasons.append("multiple-clip-cuts")
        if reasons and not any(a<=left and right<=b for a,b in verified_ranges):
            issues.append({"word_index":index,"word":word["word"],"range_us":[left,right],"crossed_cuts_us":crossed,"reasons":reasons})
    return issues


def require_review(words,draft,verified_ranges=()):
    issues=flags(words,draft,verified_ranges)
    if issues:
        raise RuntimeError("Caption audio review required for stretched words or hidden repetitions: "
                           +str([i["word_index"] for i in issues])+". Read caption-audio-review.json, stage supported corrections with review-transcript, and rebuild semantic ranges.")


def audit(work: Path,draft,transcript,config,sha):
    from capcut_tool import transcript_words,primary_track,write_json
    issues=flags(transcript_words(transcript,draft["duration"]),draft)
    if not issues:return None
    windows=set();duration=draft["duration"]
    for issue in issues:
        left,right=issue["range_us"]
        if right-left>30_000_000:
            raise RuntimeError("Caption word interval exceeds bounded audio review; re-transcribe the current timeline")
        for context in (400_000,1_200_000):windows.add((max(0,left-context),min(duration,right+context)))
        for seg in primary_track(draft)["segments"]:
            target=seg["target_timerange"];a,b=target["start"],target["start"]+target["duration"]
            if any(a<=cut<=b for cut in issue["crossed_cuts_us"]):
                windows.add((max(a,left-2_000_000),min(b,right+2_000_000)))
    records=[]
    for index,(left,right) in enumerate(sorted(windows)):
        if right<=left:continue
        audio=work/f"caption-review-{sha[:12]}-{index:03}.wav"
        extract_window(work/"timeline.wav",audio,left,right)
        result=transcribe(audio,config,speech_review=True)
        records.append({"range_us":[left,right],"audio_file":audio.name,
                        "audio_sha256":hashlib.sha256(audio.read_bytes()).hexdigest(),"transcript":result})
    report={"schema":1,"transcript_sha256":sha,"timeline_audio_sha256":hashlib.sha256((work/"timeline.wav").read_bytes()).hexdigest(),
            "issues":issues,"independent_audio_reviews":records,"note":"Recognized tokens alone do not prove acoustic start. Compare contexts and actual clip ownership; preserve repeats."}
    path=work/"caption-audio-review.json";write_json(path,report)
    return {"file":path.name,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"issue_count":len(issues)}
