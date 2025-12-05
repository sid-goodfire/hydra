#!/usr/bin/env python3
"""Test script to verify worktree_dir configuration works."""

import shutil
import sys
import tempfile
from pathlib import Path

# Add the plugin to the path
sys.path.insert(0, str(Path(__file__).parent))

from hydra_plugins.hydra_submitit_launcher.git_snapshot import (
    create_git_snapshot,
    create_snapshot_worktree,
    get_repo_root,
)


def test_worktree_default_location():
    """Test worktree creation in default location (parent of repo)."""
    print("\n[Test 1] Worktree in default location (parent of repo)")
    print("=" * 60)

    try:
        repo_root = get_repo_root()
        expected_parent = repo_root.parent

        # Create snapshot
        branch_name, _ = create_git_snapshot("test-worktree-default")

        # Create worktree with default location (None)
        workdir = create_snapshot_worktree(branch_name, ["outputs"], repo_root, None)

        print(f"✓ Worktree created: {workdir}")
        print(f"  Repo root: {repo_root}")
        print(f"  Repo parent: {expected_parent}")
        print(f"  Worktree parent: {workdir.parent.parent}")

        # Verify it's in the parent directory
        if workdir.parent.parent == expected_parent:
            print(f"✓ Worktree is in parent directory as expected")
            return True, branch_name
        else:
            print(f"✗ Worktree is NOT in parent directory")
            return False, branch_name

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False, None


def test_worktree_custom_location():
    """Test worktree creation in custom location."""
    print("\n[Test 2] Worktree in custom location")
    print("=" * 60)

    # Create a temporary directory for testing
    custom_dir = Path(tempfile.mkdtemp(prefix="test-custom-worktree-"))

    try:
        repo_root = get_repo_root()

        # Create snapshot
        branch_name, _ = create_git_snapshot("test-worktree-custom")

        # Create worktree with custom location
        workdir = create_snapshot_worktree(
            branch_name, ["outputs"], repo_root, custom_dir
        )

        print(f"✓ Worktree created: {workdir}")
        print(f"  Custom base dir: {custom_dir}")
        print(f"  Worktree parent: {workdir.parent.parent}")

        # Verify it's in the custom directory
        if workdir.parent.parent == custom_dir:
            print(f"✓ Worktree is in custom directory as expected")
            return True, branch_name
        else:
            print(f"✗ Worktree is NOT in custom directory")
            return False, branch_name

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False, None
    finally:
        # Cleanup custom directory
        if custom_dir.exists():
            shutil.rmtree(custom_dir, ignore_errors=True)


def main():
    """Run all tests."""
    print("Testing Worktree Directory Configuration")
    print("=" * 60)

    branches_to_cleanup = []

    # Test 1: Default location
    success1, branch1 = test_worktree_default_location()
    if branch1:
        branches_to_cleanup.append(branch1)

    # Test 2: Custom location
    success2, branch2 = test_worktree_custom_location()
    if branch2:
        branches_to_cleanup.append(branch2)

    # Summary
    print("\n" + "=" * 60)
    if success1 and success2:
        print("✓ All tests passed!")
        print("\nCleanup commands:")
        for branch in branches_to_cleanup:
            print(f"  git branch -D {branch}")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
