"""Regression checks for rounded media tails and timeline audio alignment."""
from pathlib import Path
import shutil
import tempfile
import unittest
import wave

from test_workflow import audio, draft, tool

@unittest.skipUnless(shutil.which('ffmpeg'), 'FFmpeg not installed')
class AudioAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='capcut-audio-alignment-')
        self.root = Path(self.temp.name)
        self.media = self.root / 'source.wav'
        self.config = tool.settings()
    def tearDown(self):
        self.temp.cleanup()
    def test_video_frame_tail_is_padded_and_reported(self):
        audio(self.media, [(0.976, True)])
        value = draft(self.media, (1_000_000,))
        value['fps'] = 30.0
        changes = tool.extract_audio(value, self.root, self.root/'output.wav', self.config)
        with wave.open(str(self.root/'output.wav')) as rendered:
            self.assertEqual(rendered.getnframes(), 16000)
            rendered.setpos(15616)
            self.assertEqual(rendered.readframes(384), b'\0\0'*384)
        self.assertEqual(changes[0]['tail_padding_samples'], 384)
    def test_real_truncation_is_refused(self):
        audio(self.media, [(0.9, True)])
        value = draft(self.media, (1_000_000,))
        value['fps'] = 30.0
        with self.assertRaisesRegex(RuntimeError, 'truncated'):
            tool.extract_audio(value, self.root, self.root/'output.wav', self.config)
    def test_audio_only_does_not_get_video_frame_allowance(self):
        audio(self.media, [(0.976, True)])
        value = draft(self.media, (1_000_000,), audio_only=True)
        value['fps'] = 30.0
        with self.assertRaisesRegex(RuntimeError, 'truncated'):
            tool.extract_audio(value, self.root, self.root/'output.wav', self.config)
    def test_each_repeated_slice_keeps_next_clip_position(self):
        audio(self.media, [(0.976, True)])
        value = draft(self.media)
        value['fps'] = 30.0
        value['tracks'][0]['segments'][1]['source_timerange']['start'] = 0
        changes = tool.extract_audio(value, self.root, self.root/'output.wav', self.config)
        with wave.open(str(self.root/'output.wav')) as rendered:
            self.assertEqual(rendered.getnframes(), 32000)
            rendered.setpos(15616)
            self.assertEqual(rendered.readframes(384), b'\0\0'*384)
            self.assertNotEqual(rendered.readframes(384), b'\0\0'*384)
        self.assertEqual(len(changes), 2)
