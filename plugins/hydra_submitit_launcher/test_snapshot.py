#!/usr/bin/env python3
"""Simple test script to verify git snapshot functionality."""

import os
import sys
from pathlib import Path

# Add the plugin to the path
sys.path.insert(0, str(Path(__file__).parent))

from hydra_plugins.hydra_submitit_launcher.git_snapshot import (
    create_git_snapshot,
    create_snapshot_worktree,
    get_repo_root,
)


def test_get_repo_root():
    """Test getting repository root."""
    try:
        repo_root = get_repo_root()
        print(f"✓ Repository root found: {repo_root}")
        return True
    except Exception as e:
        print(f"✗ Failed to get repo root: {e}")
        return False


def test_create_snapshot():
    """Test creating a git snapshot."""
    try:
        branch_name, commit_hash = create_git_snapshot("test-snapshot")
        print(f"✓ Created snapshot branch: {branch_name}")
        print(f"  Commit hash: {commit_hash[:8]}")
        return True, branch_name
    except Exception as e:
        print(f"✗ Failed to create snapshot: {e}")
        return False, None


def test_create_worktree(snapshot_branch):
    """Test creating a snapshot worktree."""
    try:
        symlink_paths = ["outputs", ".submitit"]
        workdir = create_snapshot_worktree(snapshot_branch, symlink_paths)
        print(f"✓ Created snapshot worktree: {workdir}")

        # Verify worktree exists
        if not workdir.exists():
            print(f"✗ Worktree directory doesn't exist: {workdir}")
            return False

        # Verify it's a git repo
        git_dir = workdir / ".git"
        if not git_dir.exists():
            print(f"✗ Not a git repository: {workdir}")
            return False

        print(f"✓ Worktree is valid git repository")
        return True

    except Exception as e:
        print(f"✗ Failed to create worktree: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("Testing Git Snapshot Functionality")
    print("=" * 50)

    # Test 1: Get repo root
    print("\n[Test 1] Getting repository root...")
    if not test_get_repo_root():
        print("\nTests failed: Not in a git repository")
        return 1

    # Test 2: Create snapshot
    print("\n[Test 2] Creating git snapshot...")
    success, snapshot_branch = test_create_snapshot()
    if not success:
        print("\nTests failed: Could not create snapshot")
        return 1

    # Test 3: Create worktree
    print("\n[Test 3] Creating snapshot worktree...")
    if not test_create_worktree(snapshot_branch):
        print("\nTests failed: Could not create worktree")
        return 1

    print("\n" + "=" * 50)
    print("✓ All tests passed!")
    print("\nNote: Snapshot branches remain in your repository.")
    print(f"To clean up, run: git branch -D {snapshot_branch}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
