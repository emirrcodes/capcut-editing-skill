"""An unrelated open CapCut project must not block a confirmed closed target."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from test_workflow import draft, project, transcript, tool, audio

class ProjectClosureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='capcut-project-closure-')
        self.root = Path(self.temp.name)
        self.media = self.root/'source.wav'
        audio(self.media, [(2, True)])
        self.config = tool.settings()
        font = self.root/'font.ttf'
        font.write_bytes(b'font path fixture')
        self.config['font_path'] = str(font)
    def tearDown(self):
        self.temp.cleanup()
    def test_closed_target_apply_restore_while_app_running(self):
        folder = project(self.root, draft(self.media))
        originals = {p:p.read_bytes() for p in tool.source_paths(folder)}
        work = self.root/'work'
        with patch('transcribe.transcribe', return_value=transcript()):
            tool.prepare(folder, 'subtitles', work, self.config)
        tool.write_json(work/'subtitles.json', {'transcript_sha256':tool.read_json(work/'words.json')['transcript_sha256'], 'ranges':[[1,4],[5,8]]})
        with patch.object(tool, 'is_capcut_running', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'target project'):
                tool.apply(work)
            self.assertEqual(originals, {p:p.read_bytes() for p in originals})
            self.assertFalse(list(folder.rglob('*.bak')))
            report = tool.apply(work, project_closed=True)
            self.assertEqual(report['subtitle_blocks'], 2)
            with self.assertRaisesRegex(RuntimeError, 'target project'):
                tool.restore(folder, report['backup_suffix'])
            tool.restore(folder, report['backup_suffix'], project_closed=True)
        self.assertEqual(originals, {p:p.read_bytes() for p in originals})
    def test_closure_confirmation_cannot_bypass_changed_files(self):
        folder = project(self.root, draft(self.media))
        paths = tool.source_paths(folder)
        expected = tool.snapshot(folder, paths)
        payloads = {p:p.read_bytes() for p in paths}
        paths[0].write_bytes(paths[0].read_bytes()+b' ')
        with patch.object(tool, 'is_capcut_running', return_value=True):
            with self.assertRaisesRegex(RuntimeError, 'changed after preparation'):
                tool.commit(folder, payloads, expected, 'edit', project_closed=True)
        self.assertFalse(list(folder.rglob('*.bak')))
