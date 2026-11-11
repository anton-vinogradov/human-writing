#!/usr/bin/env python3
"""Opt-in, best-effort updates for a Git-installed human-writing skill."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import time


SKILL_ROOT = Path(__file__).resolve().parent.parent
ROOT = SKILL_ROOT.parent.parent
UPSTREAM = "https://github.com/anton-vinogradov/human-writing.git"
BRANCH = "main"
INTERVAL = 24 * 60 * 60
TIMEOUT = 15
SETTING = "human-writing.autoUpdate"


def git(*args, check=True):
    env = os.environ.copy()
    # A caller's Git environment must not redirect writes into their project.
    for key in (
        "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    ):
        env.pop(key, None)
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        capture_output=True, text=True, check=check, timeout=TIMEOUT, env=env,
    )


def emit(status, reason, **details):
    print(json.dumps(dict(status=status, reason=reason, **details)))


def enabled():
    result = git("config", "--local", "--bool", "--get", SETTING, check=False)
    return result.returncode == 0 and result.stdout.strip() == "true"


def check_installation():
    # A copied skill inside another project must never update its parent repo.
    if SKILL_ROOT != ROOT / "skills" / "human-writing" or not (ROOT / ".git").is_dir():
        raise ValueError("requires a standalone Git clone; see README.md")
    top = Path(git("rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if top != ROOT.resolve():
        raise ValueError("installation is not the Git repository root")
    check_origin()


def check_origin():
    origin = git("remote", "get-url", "origin").stdout.strip()
    accepted = {UPSTREAM, UPSTREAM.removesuffix(".git")}
    if UPSTREAM == "https://github.com/anton-vinogradov/human-writing.git":
        accepted.update({
            "git@github.com:anton-vinogradov/human-writing.git",
            "ssh://git@github.com/anton-vinogradov/human-writing.git",
        })
    if origin not in accepted:
        raise ValueError("origin does not match the human-writing repository")


def check_source():
    check_origin()
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    if branch.returncode != 0 or branch.stdout.strip() != BRANCH:
        raise ValueError("updates require the main branch")


def check_clean():
    if git("status", "--porcelain", "--untracked-files=all", "--ignored").stdout:
        raise ValueError("local changes or extra files preserved; update skipped")


@contextmanager
def update_lock():
    # OS locks are released on process exit, including a crash. No stale-lock TTL.
    with (ROOT / ".git" / "human-writing-update.lock").open("a+b") as lock:
        if os.name == "nt":
            import msvcrt
            lock.seek(0, os.SEEK_END)
            if lock.tell() == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def update(force):
    if not enabled():
        emit("disabled", "automatic updates have not been enabled")
        return
    with update_lock():
        # Consent can change while another invocation is finishing.
        if not enabled():
            emit("disabled", "automatic updates have been disabled")
            return
        checked = ROOT / ".git" / "human-writing-last-check"
        try:
            last_check = float(checked.read_text())
        except (OSError, ValueError):
            last_check = 0
        now = time.time()
        if not force and 0 <= now - last_check < INTERVAL:
            emit("skipped", "already checked within the last 24 hours")
            return
        check_source()
        check_clean()
        before = git("rev-parse", "HEAD").stdout.strip()
        # Throttle failed attempts too, so offline work does not keep waiting.
        checked.write_text(str(now))
        git("fetch", "--quiet", "--no-tags", UPSTREAM, BRANCH)
        target = git("rev-parse", "FETCH_HEAD").stdout.strip()
        if target == before:
            emit("current", "already up to date")
            return
        if not enabled():
            emit("disabled", "automatic updates were disabled during the check")
            return
        check_source()
        check_clean()
        if git("rev-parse", "HEAD").stdout.strip() != before:
            raise ValueError("installation changed during the check; update skipped")
        if git("merge-base", "--is-ancestor", before, target, check=False).returncode:
            raise ValueError("local history preserved; update is not a fast-forward")
        for path in ("skills/human-writing/SKILL.md", "skills/human-writing/scripts/update.py"):
            git("cat-file", "-e", target + ":" + path)
        # Disable local merge hooks; an update only needs to replace skill files.
        git("-c", "core.hooksPath=" + os.devnull, "-c", "submodule.recurse=false",
            "merge", "--ff-only", "--no-edit", target)
        emit("updated", "reread SKILL.md before writing", old=before, new=target)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    consent = parser.add_mutually_exclusive_group()
    consent.add_argument("--enable", action="store_true", help="opt into updates from main")
    consent.add_argument("--disable", action="store_true", help="stop automatic updates")
    parser.add_argument("--force", action="store_true", help="bypass only the 24-hour interval")
    args = parser.parse_args(argv)
    try:
        check_installation()
        if args.enable or args.disable:
            if args.enable:
                check_source()
            git("config", "--local", SETTING, "true" if args.enable else "false")
            emit("enabled" if args.enable else "disabled", "preference saved for this installation")
        else:
            update(args.force)
    except ValueError as exc:
        emit("skipped", str(exc))
    except subprocess.TimeoutExpired:
        emit("skipped", "Git timed out; continue with the installed skill")
    except subprocess.CalledProcessError:
        emit("skipped", "Git check or update failed; continue with the installed skill")
    except OSError:
        emit("skipped", "installation unavailable, read-only, or busy; continue with the installed skill")


if __name__ == "__main__":
    main()
