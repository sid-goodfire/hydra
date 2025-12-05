"""Git utilities for creating code snapshots with symlinked output directories."""

import datetime
import logging
import shutil
import subprocess
import tempfile
from pathlib import Path


log = logging.getLogger(__name__)


def get_repo_root() -> Path:
    """Get the root directory of the git repository.

    Returns:
        Path to the repository root

    Raises:
        subprocess.CalledProcessError: If not in a git repository
    """
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def repo_current_branch() -> str:
    """Return the active Git branch by invoking the `git` CLI.

    Uses `git rev-parse --abbrev-ref HEAD`, which prints either the branch
    name (e.g. `main`) or `HEAD` if the repo is in a detached-HEAD state.

    Returns:
        The name of the current branch, or `HEAD` if in detached state.

    Raises:
        subprocess.CalledProcessError: If the `git` command fails.
    """
    repo_root = get_repo_root()
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def create_git_snapshot(
    branch_name_prefix: str, repo_root: Path | None = None
) -> tuple[str, str]:
    """Create a git snapshot branch with current changes.

    Creates a timestamped branch containing all current changes (staged and unstaged). Uses a
    temporary worktree to avoid affecting the current working directory. Will push the snapshot
    branch to origin if possible, but will continue without error if push permissions are lacking.

    Args:
        branch_name_prefix: Prefix for the snapshot branch name
        repo_root: Repository root path (auto-detected if None)

    Returns:
        (branch_name, commit_hash) where commit_hash is the HEAD of the snapshot branch
        (this will be the new snapshot commit if changes existed, otherwise the base commit).

    Raises:
        subprocess.CalledProcessError: If git commands fail (except for push)
    """
    if repo_root is None:
        repo_root = get_repo_root()

    # Generate timestamped branch name
    timestamp_utc = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d-%H%M%S")
    snapshot_branch = f"{branch_name_prefix}-{timestamp_utc}"

    # Create temporary worktree path
    with tempfile.TemporaryDirectory() as temp_dir:
        worktree_path = Path(temp_dir) / f"snapshot-{timestamp_utc}"

        try:
            # Create worktree with new branch
            subprocess.run(
                ["git", "worktree", "add", "-b", snapshot_branch, str(worktree_path)],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )

            # Copy current working tree to worktree (including untracked files)
            subprocess.run(
                [
                    "rsync",
                    "-a",
                    "--delete",
                    "--exclude=.git",
                    "--filter=:- .gitignore",
                    f"{repo_root}/",
                    f"{worktree_path}/",
                ],
                check=True,
                capture_output=True,
            )

            # Stage all changes in the worktree
            subprocess.run(
                ["git", "add", "-A"], cwd=worktree_path, check=True, capture_output=True
            )

            # Check if there are changes to commit
            diff_result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=worktree_path,
                capture_output=True,
            )

            # Commit changes if any exist
            if diff_result.returncode != 0:  # Non-zero means there are changes
                subprocess.run(
                    ["git", "commit", "-m", f"Snapshot {timestamp_utc}", "--no-verify"],
                    cwd=worktree_path,
                    check=True,
                    capture_output=True,
                )

            # Get the commit hash of HEAD (either new commit or base commit if nothing changed)
            rev_parse = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=worktree_path,
                check=True,
                capture_output=True,
                text=True,
            )
            commit_hash = rev_parse.stdout.strip()

            # Try push (non-fatal if fails)
            try:
                subprocess.run(
                    ["git", "push", "-u", "origin", snapshot_branch],
                    cwd=worktree_path,
                    check=True,
                    capture_output=True,
                )
                log.info(
                    f"Successfully pushed snapshot branch '{snapshot_branch}' to origin"
                )
            except subprocess.CalledProcessError as e:
                log.warning(
                    f"Could not push snapshot branch '{snapshot_branch}' to origin. "
                    f"The branch was created locally but won't be accessible to other users. "
                    f"Error: {e.stderr.decode().strip() if e.stderr else 'Unknown error'}"
                )

        finally:
            # Clean up worktree (branch remains in main repo)
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_path)],
                cwd=repo_root,
                check=True,
                capture_output=True,
            )

    return snapshot_branch, commit_hash


def create_snapshot_worktree(
    snapshot_branch: str,
    symlink_paths: list[str],
    repo_root: Path | None = None,
) -> Path:
    """Create a worktree from a snapshot branch with symlinked output directories.

    Args:
        snapshot_branch: Name of the snapshot branch to clone
        symlink_paths: List of paths (relative to repo root) to symlink back to original.
                      e.g., ["assets", "outputs", "wandb", ".env"]
        repo_root: Repository root path (auto-detected if None)

    Returns:
        Path to the snapshot worktree directory

    Raises:
        subprocess.CalledProcessError: If git commands fail
    """
    if repo_root is None:
        repo_root = get_repo_root()

    # Create temporary directory for the snapshot worktree
    temp_dir = Path(tempfile.mkdtemp(prefix="hypersteer-job-"))
    snapshot_workdir = temp_dir / "code"

    try:
        # Clone the snapshot branch
        subprocess.run(
            [
                "git",
                "clone",
                "-b",
                snapshot_branch,
                str(repo_root),
                str(snapshot_workdir),
            ],
            check=True,
            capture_output=True,
        )
        log.debug(
            f"Cloned snapshot branch '{snapshot_branch}' to {snapshot_workdir}"
        )

        # Create symlinks for output directories
        for rel_path in symlink_paths:
            target_path = repo_root / rel_path
            link_path = snapshot_workdir / rel_path

            # Skip if target doesn't exist in original
            if not target_path.exists():
                log.debug(f"Symlink target doesn't exist: {target_path}, skipping")
                continue

            # Remove if it exists in snapshot (from git clone)
            if link_path.exists():
                if link_path.is_dir() and not link_path.is_symlink():
                    shutil.rmtree(link_path)
                else:
                    link_path.unlink()

            # Create symlink
            link_path.symlink_to(target_path)
            log.debug(f"Symlinked {rel_path} → {target_path}")

        log.info(
            f"Created snapshot worktree:\n"
            f"  Branch: {snapshot_branch}\n"
            f"  Code dir: {snapshot_workdir}\n"
            f"  Symlinks: {symlink_paths}"
        )

        return snapshot_workdir

    except Exception as e:
        # Cleanup on failure
        if snapshot_workdir.exists():
            shutil.rmtree(snapshot_workdir)
        raise RuntimeError(f"Failed to create snapshot worktree: {e}") from e


def cleanup_snapshot_worktree(snapshot_workdir: Path) -> None:
    """Clean up a snapshot worktree directory.

    Args:
        snapshot_workdir: Path to the snapshot worktree to remove
    """
    if snapshot_workdir.exists():
        # Get the parent temp directory (created by mkdtemp)
        temp_dir = snapshot_workdir.parent
        shutil.rmtree(temp_dir)
        log.debug(f"Cleaned up snapshot worktree: {snapshot_workdir}")
