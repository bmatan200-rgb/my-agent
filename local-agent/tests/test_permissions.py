"""Current one-time authorization policy tests. No persistent grants are issued."""
import os
import tempfile
import unittest
from pathlib import Path

import permissions


class PermissionTests(unittest.TestCase):
    def setUp(self):
        safe_base = Path.home() / ".personal-ai-agent" / "workspace"
        safe_base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="agent-unit-", dir=safe_base)
        self.root = Path(self.tmp.name) / "documents"
        self.root.mkdir()
        self.grants = Path(self.tmp.name) / "permissions.json"
        (self.root / "notes.txt").write_text("hello", encoding="utf-8")
        (self.root / "id_rsa.pem").write_text("private", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_denies_without_approval(self):
        with self.assertRaises(PermissionError):
            permissions.list_files(str(self.root), self.grants)

    def test_approved_listing_skips_sensitive_files(self):
        files = permissions.list_files(str(self.root), self.grants, one_time_root=self.root)
        self.assertEqual([str(self.root / "notes.txt")], files)

    def test_one_time_approval_does_not_persist(self):
        text = permissions.read_file(str(self.root / "notes.txt"), self.grants, one_time_root=self.root)
        self.assertEqual("hello", text)
        with self.assertRaises(PermissionError):
            permissions.read_file(str(self.root / "notes.txt"), self.grants)

    def test_approval_is_directory_scoped(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("hidden", encoding="utf-8")
        with self.assertRaises(PermissionError):
            permissions.read_file(str(outside), self.grants, one_time_root=self.root)

    def test_sensitive_file_denied_even_with_approval(self):
        with self.assertRaises(PermissionError):
            permissions.read_file(str(self.root / "id_rsa.pem"), self.grants, one_time_root=self.root)

    def test_windows_system_directory_blocked(self):
        system_root = os.environ.get("SystemRoot", r"C:\Windows")
        if os.name != "nt":
            self.skipTest("Windows-only security boundary")
        with self.assertRaises(PermissionError):
            permissions.resolve_user_path(system_root)


if __name__ == "__main__":
    unittest.main()