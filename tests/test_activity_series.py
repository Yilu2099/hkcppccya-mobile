"""Exercise the actual maintenance migration and rollback without server credentials."""
import ast
import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import tarfile
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "admin/maintenance.py"
tree = ast.parse(SOURCE.read_text())
namespace = dict(hashlib=hashlib, json=json, os=os, tarfile=tarfile,
                 tempfile=tempfile, time=time)
functions = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)], type_ignores=[])
exec(compile(functions, str(SOURCE), "exec"), namespace)
migrate = namespace["migrate_legacy_series"]


class ActivitySeriesMigrationTests(unittest.TestCase):
    def test_missing_legacy_tags_migrate_once_without_changing_article_content(self):
        expected = {1084: "tour", 1082: "national", 1087: "policy",
                    1088: "policy", 1085: "mentor", 1086: "mentor"}
        rows = [dict(id=key, title="Keep title", body=["Keep body"], images=["keep.webp"]) for key in expected]
        rows.append(dict(id=1234, title="Unrelated"))
        before = copy.deepcopy(rows)
        self.assertEqual(set(migrate(rows)), set(expected))
        for old, new in zip(before, rows):
            self.assertEqual({k:v for k,v in new.items() if k != "tag"}, old)
            self.assertEqual(new.get("tag"), expected.get(new["id"]))
        self.assertEqual(migrate(rows), [])

    def test_explicit_clear_and_existing_choices_survive_repeat_publication(self):
        rows = [dict(id=1084, tag=""), dict(id=1082, tag="mentor"),
                dict(id=1085, tag=None)]
        before = copy.deepcopy(rows)
        self.assertEqual(migrate(rows), [])
        self.assertEqual(migrate(rows), [])
        self.assertEqual(rows, before)

    def publication(self, root, public, update):
        namespace.update(ROOT=root, PUBLIC=public, LOCK=contextlib.nullcontext(),
                         validate=lambda name, rows: None, update_site=update)
        return namespace["publish"]()

    def prepare(self, folder):
        root, public = Path(folder)/"source", Path(folder)/"public"
        (root/"assets").mkdir(parents=True)
        public.mkdir()
        (public/"index.html").write_text("old public")
        (root/"assets/news.json").write_text('[{"id":1084,"title":"Keep"}]')
        (root/"assets/site-content.json").write_text('{"keep":true}')
        return root, public

    def test_publication_saves_source_backup_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            root, public = self.prepare(folder)
            before = (root/"assets/news.json").read_bytes()
            self.publication(root, public, lambda: (public/"index.html").write_text("new public"))
            self.assertEqual(json.loads((root/"assets/news.json").read_text())[0]["tag"], "tour")
            backups = list((root/"admin/backups/published").glob("*.news.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), before)
            # The editor's explicit clear remains cleared on the next maintenance run.
            (root/"assets/news.json").write_text('[{"id":1084,"title":"Keep","tag":""}]')
            self.publication(root, public, lambda: None)
            self.assertEqual(json.loads((root/"assets/news.json").read_text())[0]["tag"], "")
            self.assertEqual(len(list((root/"admin/backups/published").glob("*.news.json"))), 1)

    def test_failed_publication_restores_source_bytes_and_previous_public_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root, public = self.prepare(folder)
            before = (root/"assets/news.json").read_bytes()
            def fail():
                (public/"index.html").write_text("partial")
                raise RuntimeError("simulated build failure")
            with self.assertRaisesRegex(RuntimeError, "simulated"):
                self.publication(root, public, fail)
            self.assertEqual((root/"assets/news.json").read_bytes(), before)
            self.assertEqual((public/"index.html").read_text(), "old public")

    def test_unrelated_source_change_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            root, public = self.prepare(folder)
            def changed():
                (root/"assets/site-content.json").write_text('{"unexpected":true}')
            with self.assertRaisesRegex(RuntimeError, "受保护资料"):
                self.publication(root, public, changed)


if __name__ == "__main__":
    unittest.main()
