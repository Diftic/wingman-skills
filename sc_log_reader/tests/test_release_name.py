"""Canonical release naming keeps the existing update and host contracts usable."""
import importlib
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ReleaseNameTests(unittest.TestCase):
    def test_canonical_package_reads_both_instruction_identifiers(self):
        reader = importlib.import_module('sc_log_reader.reader')
        raw = reader.bundled_bytes()
        for package_id in ('sc_log_reader', 'sc_log_reader_2'):
            data = json.loads(raw)
            data['package_id'] = package_id
            self.assertEqual(reader.Instructions.load(json.dumps(data).encode()).data['package_id'], package_id)
        data['package_id'] = 'some_other_skill'
        with self.assertRaises(reader.InstructionError):
            reader.Instructions.load(json.dumps(data).encode())

    def test_saved_legacy_class_name_remains_a_lazy_alias(self):
        base = types.ModuleType('skills.skill_base')
        base.Skill = type('Skill', (), {})
        wrapper = ROOT / 'integrations/wingman_target/main.py'
        namespace = {'__file__': str(wrapper), '__name__': 'rename_probe'}
        with patch.dict(sys.modules, {'skills.skill_base': base}):
            exec(compile(wrapper.read_bytes(), str(wrapper), 'exec'), namespace)
        self.assertEqual(namespace['SCLogReader'].__name__, 'SCLogReader')
        self.assertIs(namespace['SCLogReader2'], namespace['SCLogReader'])

    def test_new_catalog_uses_canonical_name(self):
        config = (ROOT / 'integrations/wingman_target/default_config.yaml').read_text()
        self.assertIn('name: SCLogReader\n', config)
        self.assertIn('module: skills.sc_log_reader.main\n', config)
        self.assertNotIn('SCLogReader2', config)

    def test_process_registry_is_shared_with_pre_rename_reader(self):
        boundary = importlib.import_module('sc_log_reader.host_boundary')
        self.assertIs(boundary._registry, sys.modules['_sc_log_reader_2_host_registry_v1'])
        self.assertIs(boundary._registry, sys.modules['_sc_log_reader_host_registry_v1'])

    def test_existing_instruction_objects_and_rejections_survive(self):
        updates = importlib.import_module('sc_log_reader.updates')
        raw = (ROOT / 'updates/instructions.json').read_bytes()
        url = 'https://raw.githubusercontent.com/example/reader/main/instructions.json'
        with tempfile.TemporaryDirectory() as tmp:
            manager = updates.UpdateManager(tmp, url, fetch=lambda _: raw)
            original = manager.startup()
            candidate = manager.check()
            manager.approve(candidate['sha256'])
            restarted = updates.UpdateManager(tmp, url)
            self.assertEqual(restarted.startup().revision, 7)
            path = Path(tmp) / 'manifest.json'
            manifest = json.loads(path.read_text())
            manifest['rejected_revisions'] = [6]
            path.write_text(json.dumps(manifest))
            next_start = updates.UpdateManager(tmp, url)
            self.assertEqual(next_start.startup().raw, raw)
            status = next_start.status()
            self.assertEqual(json.loads(path.read_text())['previous'], updates.digest(original.raw))
            self.assertEqual(status['rejected_revisions'], [6])
            self.assertEqual(next_start.rollback()['sha256'], updates.digest(original.raw))
