"""Exercise the updater against disposable repositories without network access."""

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SKILL_PATH = Path("skills") / "human-writing"
SCRIPT = Path(__file__).resolve().parents[1] / SKILL_PATH / "scripts" / "update.py"
SPEC = importlib.util.spec_from_file_location("human_writing_updater", SCRIPT)
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="human-writing-update-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.remote = self.base / "upstream.git"
        self.source = self.base / "source"
        self.install = self.base / "installed"
        self.source_skill = self.source / SKILL_PATH
        self.install_skill = self.install / SKILL_PATH
        self.git(self.base, "init", "--bare", str(self.remote))
        self.git(self.base, "init", "-b", "main", str(self.source))
        self.configure_author(self.source)
        self.source_skill.mkdir(parents=True)
        (self.source_skill / "SKILL.md").write_text("Original skill\n", encoding="utf-8")
        (self.source_skill / "agents").mkdir()
        (self.source_skill / "agents" / "openai.yaml").write_text("version: 1\n", encoding="utf-8")
        (self.source_skill / "scripts").mkdir()
        (self.source_skill / "scripts" / "update.py").write_text(SCRIPT.read_text(), encoding="utf-8")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-m", "Initial skill")
        self.git(self.source, "remote", "add", "origin", str(self.remote))
        self.git(self.source, "push", "-u", "origin", "main")
        self.git(self.remote, "symbolic-ref", "HEAD", "refs/heads/main")
        self.git(self.base, "clone", str(self.remote), str(self.install))
        self.configure_author(self.install)
        self.initial_head = self.head()
        for name, value in [
            ("ROOT", self.install),
            ("SKILL_ROOT", self.install_skill),
            ("UPSTREAM", str(self.remote)),
        ]:
            patcher = mock.patch.object(updater, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def git(self, directory, *args, check=True):
        result = subprocess.run(
            ["git", "-C", str(directory), *args],
            check=check,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self.git_environment(),
        )
        return result.stdout.strip() if check else result

    @staticmethod
    def git_environment():
        # Ignore host aliases, signing settings, and global excludes in fixtures.
        environment = os.environ.copy()
        for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE"):
            environment.pop(key, None)
        environment.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_TERMINAL_PROMPT="0",
        )
        return environment

    def configure_author(self, directory):
        self.git(directory, "config", "user.name", "Updater test")
        self.git(directory, "config", "user.email", "updater@example.invalid")

    def head(self):
        return self.git(self.install, "rev-parse", "HEAD")

    def enable(self):
        self.git(self.install, "config", "--local", "human-writing.autoUpdate", "true")

    def advance_upstream(self):
        (self.source_skill / "SKILL.md").write_text("Updated skill\n", encoding="utf-8")
        (self.source_skill / "agents" / "openai.yaml").write_text("version: 2\n", encoding="utf-8")
        (self.source_skill / "references").mkdir(exist_ok=True)
        (self.source_skill / "references" / "new.txt").write_text("New support file\n", encoding="utf-8")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-m", "Update skill and support files")
        self.git(self.source, "push", "origin", "main")
        return self.git(self.source, "rev-parse", "HEAD")

    def invoke(self, *args, module=updater):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), mock.patch.dict(
            "os.environ", self.git_environment()
        ):
            module.main(list(args))
        lines = output.getvalue().splitlines()
        self.assertEqual(len(lines), 1, output.getvalue())
        result = json.loads(lines[0])
        self.assertIsInstance(result.get("reason"), str)
        return result

    def assert_untouched(self, head=None):
        self.assertEqual(self.head(), head or self.initial_head)
        self.assertEqual(
            (self.install_skill / "SKILL.md").read_text(encoding="utf-8"), "Original skill\n"
        )

    def test_disabled_by_default_and_force_does_not_grant_consent(self):
        self.advance_upstream()
        for args in [(), ("--force",)]:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args)["status"], "disabled")
                self.assert_untouched()
        self.assertFalse((self.install / ".git" / "human-writing-last-check").exists())

    def test_enable_and_disable_are_local_and_do_not_update(self):
        self.advance_upstream()
        self.assertEqual(self.invoke("--enable")["status"], "enabled")
        self.assertEqual(
            self.git(self.install, "config", "--local", "--bool", "human-writing.autoUpdate"),
            "true",
        )
        self.assert_untouched()
        self.assertEqual(self.invoke("--disable")["status"], "disabled")
        self.assertEqual(self.invoke("--force")["status"], "disabled")
        self.assert_untouched()

    def test_update_fast_forwards_skill_and_all_support_files(self):
        self.enable()
        expected_head = self.advance_upstream()
        result = self.invoke()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["old"], self.initial_head)
        self.assertEqual(result["new"], expected_head)
        self.assertEqual(self.head(), expected_head)
        self.assertEqual((self.install_skill / "SKILL.md").read_text(), "Updated skill\n")
        self.assertEqual((self.install_skill / "agents" / "openai.yaml").read_text(), "version: 2\n")
        self.assertEqual(
            (self.install_skill / "references" / "new.txt").read_text(), "New support file\n"
        )
        self.assertEqual(self.git(self.install, "status", "--porcelain"), "")

    def test_update_through_skill_directory_symlink(self):
        self.enable()
        expected_head = self.advance_upstream()
        link = self.base / "linked-skill"
        try:
            link.symlink_to(self.install_skill, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"Directory symlinks are unavailable: {exc}")
        linked_spec = importlib.util.spec_from_file_location(
            "linked_human_writing_updater", link / "scripts" / "update.py"
        )
        linked_updater = importlib.util.module_from_spec(linked_spec)
        linked_spec.loader.exec_module(linked_updater)
        with mock.patch.object(linked_updater, "UPSTREAM", str(self.remote)):
            self.assertEqual(self.invoke(module=linked_updater)["status"], "updated")
        self.assertEqual(self.head(), expected_head)
        self.assertEqual((link / "SKILL.md").read_text(), "Updated skill\n")
        self.assertEqual((self.install_skill / "SKILL.md").read_text(), "Updated skill\n")

    def test_missing_upstream_skill_keeps_installed_version(self):
        self.enable()
        self.git(self.source, "rm", str(SKILL_PATH / "SKILL.md"))
        self.git(self.source, "commit", "-m", "Remove required skill file")
        self.git(self.source, "push", "origin", "main")
        incomplete_head = self.git(self.source, "rev-parse", "HEAD")
        self.assertEqual(self.invoke()["status"], "skipped")
        self.assertEqual(self.git(self.install, "rev-parse", "FETCH_HEAD"), incomplete_head)
        self.assert_untouched()
        self.assertEqual(self.git(self.install, "status", "--porcelain"), "")

    def test_missing_upstream_updater_keeps_installed_version(self):
        self.enable()
        installed_script = self.install_skill / "scripts" / "update.py"
        script_before = installed_script.read_bytes()
        self.git(self.source, "rm", str(SKILL_PATH / "scripts" / "update.py"))
        self.git(self.source, "commit", "-m", "Remove required updater file")
        self.git(self.source, "push", "origin", "main")
        incomplete_head = self.git(self.source, "rev-parse", "HEAD")
        self.assertEqual(self.invoke()["status"], "skipped")
        self.assertEqual(self.git(self.install, "rev-parse", "FETCH_HEAD"), incomplete_head)
        self.assert_untouched()
        self.assertEqual(installed_script.read_bytes(), script_before)
        self.assertEqual(self.git(self.install, "status", "--porcelain"), "")

    def test_current_check_throttles_later_checks_and_force_bypasses_time(self):
        self.enable()
        self.assertEqual(self.invoke()["status"], "current")
        state = self.install / ".git" / "human-writing-last-check"
        checked_at = state.read_text()
        self.assertGreater(float(checked_at), 0)
        expected_head = self.advance_upstream()
        self.assertEqual(self.invoke()["status"], "skipped")
        self.assert_untouched()
        self.assertEqual(state.read_text(), checked_at)
        self.assertEqual(self.invoke("--force")["status"], "updated")
        self.assertEqual(self.head(), expected_head)

    def test_expired_daily_check_updates(self):
        self.enable()
        (self.install / ".git" / "human-writing-last-check").write_text("1\n")
        expected_head = self.advance_upstream()
        self.assertEqual(self.invoke()["status"], "updated")
        self.assertEqual(self.head(), expected_head)

    def test_failed_fetch_preserves_files_and_is_also_throttled(self):
        self.enable()
        expected_head = self.advance_upstream()
        unavailable = self.base / "temporarily-unavailable.git"
        self.remote.rename(unavailable)
        try:
            self.assertEqual(self.invoke()["status"], "skipped")
            self.assert_untouched()
            state = self.install / ".git" / "human-writing-last-check"
            checked_at = state.read_text()
            self.assertGreater(float(checked_at), 0)
        finally:
            unavailable.rename(self.remote)
        self.assertEqual(self.invoke()["status"], "skipped")
        self.assert_untouched()
        self.assertEqual(state.read_text(), checked_at)
        self.assertEqual(self.invoke("--force")["status"], "updated")
        self.assertEqual(self.head(), expected_head)

    def test_modified_tracked_file_is_preserved_even_with_force(self):
        self.enable()
        self.advance_upstream()
        skill = self.install_skill / "SKILL.md"
        skill.write_text("My local changes\n", encoding="utf-8")
        for args in [(), ("--force",)]:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args)["status"], "skipped")
                self.assertEqual(skill.read_text(), "My local changes\n")
                self.assertEqual(self.head(), self.initial_head)

    def test_untracked_file_is_preserved_even_with_force(self):
        self.enable()
        self.advance_upstream()
        reference = self.install_skill / "references" / "new.txt"
        reference.parent.mkdir()
        reference.write_text("My untracked support file\n", encoding="utf-8")
        self.assertEqual(self.invoke("--force")["status"], "skipped")
        self.assert_untouched()
        self.assertEqual(reference.read_text(), "My untracked support file\n")

    def test_staged_edit_is_preserved_even_with_force(self):
        self.enable()
        self.advance_upstream()
        skill = self.install_skill / "SKILL.md"
        skill.write_text("Staged local changes\n", encoding="utf-8")
        self.git(self.install, "add", str(SKILL_PATH / "SKILL.md"))
        staged_before = self.git(self.install, "diff", "--cached")
        self.assertEqual(self.invoke("--force")["status"], "skipped")
        self.assertEqual(self.head(), self.initial_head)
        self.assertEqual(skill.read_text(), "Staged local changes\n")
        self.assertEqual(self.git(self.install, "diff", "--cached"), staged_before)

    def test_ignored_file_also_prevents_updates(self):
        self.enable()
        self.advance_upstream()
        (self.install / ".git" / "info" / "exclude").write_text("local-cache/\n")
        cache = self.install / "local-cache" / "notes.txt"
        cache.parent.mkdir()
        cache.write_text("Keep this cache\n", encoding="utf-8")
        self.assertEqual(self.invoke("--force")["status"], "skipped")
        self.assert_untouched()
        self.assertEqual(cache.read_text(), "Keep this cache\n")

    def test_divergent_local_commit_is_preserved(self):
        self.enable()
        local = self.install / "local.txt"
        local.write_text("Committed local work\n", encoding="utf-8")
        self.git(self.install, "add", "local.txt")
        self.git(self.install, "commit", "-m", "Keep local work")
        local_head = self.head()
        self.advance_upstream()
        self.assertEqual(self.invoke("--force")["status"], "skipped")
        self.assert_untouched(local_head)
        self.assertEqual(local.read_text(), "Committed local work\n")
        self.assertEqual(self.git(self.install, "status", "--porcelain"), "")

    def test_local_commit_ahead_of_upstream_is_preserved(self):
        self.enable()
        (self.install / "local.txt").write_text("Committed local work\n", encoding="utf-8")
        self.git(self.install, "add", "local.txt")
        self.git(self.install, "commit", "-m", "Keep local work")
        local_head = self.head()
        self.assertIn(self.invoke("--force")["status"], {"current", "skipped"})
        self.assert_untouched(local_head)
        self.assertEqual((self.install / "local.txt").read_text(), "Committed local work\n")

    def test_copied_skill_cannot_change_an_unrelated_project(self):
        project = self.base / "unrelated-project"
        self.git(self.base, "init", "-b", "main", str(project))
        self.configure_author(project)
        self.git(project, "remote", "add", "origin", str(self.base / "other.git"))
        self.git(project, "config", "--local", "human-writing.autoUpdate", "true")
        copied_skill = project / SKILL_PATH
        shutil.copytree(self.install_skill, copied_skill)
        (project / "project.txt").write_text("Project content\n", encoding="utf-8")
        self.git(project, "add", ".")
        self.git(project, "commit", "-m", "Project with a copied skill")
        (project / "project.txt").write_text("Staged project changes\n", encoding="utf-8")
        self.git(project, "add", "project.txt")

        def snapshot_project():
            return {
                path.relative_to(project): path.read_bytes()
                for path in project.rglob("*")
                if path.is_file()
            }

        before = snapshot_project()
        for args in [(), ("--enable",), ("--disable",), ("--force",)]:
            with self.subTest(args=args):
                result = subprocess.run(
                    [sys.executable, "-B", str(copied_skill / "scripts" / "update.py"), *args],
                    cwd=project,
                    env=self.git_environment(),
                    check=True,
                    text=True,
                    capture_output=True,
                    timeout=10,
                )
                self.assertEqual(json.loads(result.stdout)["status"], "skipped")
                self.assertEqual(snapshot_project(), before)

    def test_non_main_branch_is_not_updated(self):
        self.enable()
        self.advance_upstream()
        self.git(self.install, "checkout", "-b", "my-work")
        self.assertEqual(self.invoke("--force")["status"], "skipped")
        self.assert_untouched()
        self.assertEqual(self.git(self.install, "branch", "--show-current"), "my-work")

    def test_auto_update_can_be_disabled_on_another_branch(self):
        self.enable()
        self.git(self.install, "checkout", "-b", "my-work")
        self.assertEqual(self.invoke("--disable")["status"], "disabled")
        self.assertEqual(
            self.git(self.install, "config", "--local", "--bool", "human-writing.autoUpdate"),
            "false",
        )
        self.assert_untouched()
        self.assertEqual(self.git(self.install, "branch", "--show-current"), "my-work")

    def test_detached_head_is_not_updated(self):
        self.enable()
        self.advance_upstream()
        self.git(self.install, "checkout", "--detach")
        self.assertEqual(self.invoke("--force")["status"], "skipped")
        self.assert_untouched()
        self.assertEqual(self.git(self.install, "branch", "--show-current"), "")

    def test_unexpected_origin_is_not_updated(self):
        self.enable()
        self.advance_upstream()
        self.git(self.install, "remote", "set-url", "origin", str(self.base / "other.git"))
        self.assertEqual(self.invoke("--force")["status"], "skipped")
        self.assert_untouched()

    def test_edit_made_during_fetch_prevents_merge(self):
        self.enable()
        self.advance_upstream()
        real_git = updater.git
        skill = self.install_skill / "SKILL.md"

        def edit_after_fetch(*args, **kwargs):
            result = real_git(*args, **kwargs)
            if args[0] == "fetch":
                skill.write_text("Edit made while fetching\n", encoding="utf-8")
            return result

        with mock.patch.object(updater, "git", side_effect=edit_after_fetch):
            self.assertEqual(self.invoke()["status"], "skipped")
        self.assertEqual(self.head(), self.initial_head)
        self.assertEqual(skill.read_text(), "Edit made while fetching\n")

    def test_consent_revoked_during_fetch_prevents_merge(self):
        self.enable()
        self.advance_upstream()
        real_git = updater.git

        def disable_after_fetch(*args, **kwargs):
            result = real_git(*args, **kwargs)
            if args[0] == "fetch":
                self.git(self.install, "config", "--local", "human-writing.autoUpdate", "false")
            return result

        with mock.patch.object(updater, "git", side_effect=disable_after_fetch):
            self.assertEqual(self.invoke()["status"], "disabled")
        self.assert_untouched()

    def test_concurrent_invocation_skips_while_lock_is_held(self):
        self.enable()
        self.advance_upstream()
        with updater.update_lock():
            self.assertEqual(self.invoke("--force")["status"], "skipped")
        self.assert_untouched()
        self.assertFalse((self.install / ".git" / "human-writing-last-check").exists())
        self.assertEqual(self.invoke()["status"], "updated")

    def test_fetch_timeout_keeps_installed_skill_and_throttles_retry(self):
        self.enable()
        self.advance_upstream()
        real_git = updater.git

        def time_out_fetch(*args, **kwargs):
            if args[0] == "fetch":
                raise subprocess.TimeoutExpired(["git", *args], updater.TIMEOUT)
            return real_git(*args, **kwargs)

        with mock.patch.object(updater, "git", side_effect=time_out_fetch):
            self.assertEqual(self.invoke()["status"], "skipped")
        self.assert_untouched()
        self.assertEqual(self.invoke()["status"], "skipped")
        self.assert_untouched()

    def test_child_process_ignores_caller_repository_git_environment(self):
        self.enable()
        self.git(
            self.install, "remote", "set-url", "origin",
            "https://github.com/anton-vinogradov/human-writing.git",
        )
        self.git(self.source, "config", "--local", "human-writing.autoUpdate", "true")
        source_config_before = (self.source / ".git" / "config").read_bytes()
        source_index_before = (self.source / ".git" / "index").read_bytes()
        environment = self.git_environment()
        environment.update(
            GIT_DIR=str(self.source / ".git"),
            GIT_COMMON_DIR=str(self.source / ".git"),
            GIT_WORK_TREE=str(self.source),
            GIT_INDEX_FILE=str(self.source / ".git" / "index"),
        )
        result = subprocess.run(
            [sys.executable, "-B", str(self.install_skill / "scripts" / "update.py"), "--disable"],
            cwd=self.source,
            env=environment,
            check=True,
            text=True,
            capture_output=True,
            timeout=10,
        )
        self.assertEqual(json.loads(result.stdout)["status"], "disabled")
        self.assertEqual(
            self.git(self.install, "config", "--local", "--bool", "human-writing.autoUpdate"),
            "false",
        )
        self.assertEqual((self.source / ".git" / "config").read_bytes(), source_config_before)
        self.assertEqual((self.source / ".git" / "index").read_bytes(), source_index_before)
        self.assert_untouched()

    def test_fetch_cannot_write_objects_into_callers_repository(self):
        self.enable()
        reviewed = self.base / "reviewed-project"
        self.git(self.base, "init", "-b", "main", str(reviewed))
        self.configure_author(reviewed)
        (reviewed / "project.txt").write_text("Unrelated project\n", encoding="utf-8")
        self.git(reviewed, "add", ".")
        self.git(reviewed, "commit", "-m", "Unrelated project history")
        objects = reviewed / ".git" / "objects"

        def snapshot_objects():
            return {
                path.relative_to(objects): path.read_bytes()
                for path in objects.rglob("*")
                if path.is_file()
            }

        objects_before = snapshot_objects()
        expected_head = self.advance_upstream()
        # The alternate makes existing installed objects readable if a regression
        # sends fetch's new object writes into the unrelated primary directory.
        with mock.patch.dict(
            os.environ,
            {
                "GIT_OBJECT_DIRECTORY": str(objects),
                "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(self.install / ".git" / "objects"),
            },
        ):
            self.assertEqual(self.invoke()["status"], "updated")
        self.assertEqual(snapshot_objects(), objects_before)
        self.assertEqual(self.head(), expected_head)
        self.git(self.install, "fsck", "--full")
        self.assertEqual(
            self.git(self.install, "cat-file", "-p", f"HEAD:{SKILL_PATH.as_posix()}/SKILL.md"), "Updated skill"
        )
        self.assertEqual(
            self.git(self.install, "cat-file", "-p", f"HEAD:{SKILL_PATH.as_posix()}/references/new.txt"),
            "New support file",
        )


if __name__ == "__main__":
    unittest.main()
