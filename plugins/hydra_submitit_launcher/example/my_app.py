# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
import os
import subprocess
import time
from pathlib import Path

import hydra
import submitit
from omegaconf import DictConfig

log = logging.getLogger(__name__)


def get_git_info():
    """Get current git branch and commit hash."""
    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return branch, commit
    except Exception:
        return "unknown", "unknown"


@hydra.main(version_base=None, config_path=".", config_name="config")
def my_app(cfg: DictConfig) -> None:
    env = submitit.JobEnvironment()
    cwd = Path.cwd()
    branch, commit = get_git_info()

    # Print execution environment info
    log.info("=" * 70)
    log.info(f"Task: {cfg.task}")
    log.info(f"Process ID: {os.getpid()}")
    log.info(f"Job ID: {env.job_id}")
    log.info(f"Working Directory: {cwd}")
    log.info(f"Git Branch: {branch}")
    log.info(f"Git Commit: {commit}")

    # Check if running in a snapshot
    if "hydra-job-" in str(cwd):
        log.info("🚀 RUNNING IN SNAPSHOT WORKTREE")
        log.info(f"   Snapshot dir: {cwd}")

        # Show symlinks
        symlinks = [p for p in cwd.iterdir() if p.is_symlink()]
        if symlinks:
            log.info("   Symlinked directories:")
            for link in symlinks:
                target = link.resolve()
                log.info(f"     {link.name} -> {target}")
    else:
        log.info("Running in original repository")

    log.info("=" * 70)

    # Do some work
    log.info(f"Starting task {cfg.task}...")
    time.sleep(2)

    # Write a test output file
    output_file = Path("test_output.txt")
    with open(output_file, "w") as f:
        f.write(f"Task {cfg.task} completed successfully!\n")
        f.write(f"Working directory: {cwd}\n")
        f.write(f"Git branch: {branch}\n")
        f.write(f"Git commit: {commit}\n")

    log.info(f"✓ Task {cfg.task} completed! Output written to {output_file}")


if __name__ == "__main__":
    my_app()
