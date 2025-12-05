# Git Snapshot Implementation Summary

## Overview

Successfully implemented git snapshot functionality directly into the Hydra Submitit Launcher plugin. This allows SLURM jobs to run from isolated code snapshots while keeping all outputs in the original directory via symlinks.

## Files Modified/Created

### 1. `hydra_plugins/hydra_submitit_launcher/git_snapshot.py` (NEW)
Core git snapshot utilities providing:
- `get_repo_root()`: Find git repository root
- `repo_current_branch()`: Get current git branch
- `create_git_snapshot()`: Create timestamped snapshot branch with current changes
- `create_snapshot_worktree()`: Create isolated worktree with symlinked outputs
- `cleanup_snapshot_worktree()`: Clean up snapshot directories

**Key Features:**
- Uses temporary worktrees to avoid affecting main repo
- Captures all changes (staged, unstaged, and untracked files)
- Automatically pushes branches to remote (with graceful fallback)
- Creates symlinks for specified paths (outputs, logs, etc.)

### 2. `hydra_plugins/hydra_submitit_launcher/config.py` (MODIFIED)
Added `SnapshotConfig` dataclass:
```python
@dataclass
class SnapshotConfig:
    enabled: bool = False
    branch_prefix: str = "slurm-job"
    symlink_paths: List[str] = field(
        default_factory=lambda: ["outputs", "multirun", ".submitit"]
    )
    push_to_remote: bool = True
```

Integrated into `SlurmQueueConf`:
```python
snapshot: SnapshotConfig = field(default_factory=SnapshotConfig)
```

### 3. `hydra_plugins/hydra_submitit_launcher/submitit_launcher.py` (MODIFIED)
Enhanced `BaseSubmititLauncher.__call__()` method to:
1. Check if snapshot is enabled via config
2. Create git snapshot branch (once per launch)
3. Create worktree with symlinks for each job
4. Change working directory to snapshot before job execution
5. Restore working directory after job completes

**Implementation Details:**
- Snapshot branch created once and shared across array jobs
- Each job gets its own worktree instance
- Working directory change is transparent to user code
- Graceful fallback if snapshot creation fails
- Proper cleanup in finally block

### 4. `example/config_snapshot.yaml` (NEW)
Example configuration showing how to enable and configure snapshots:
```yaml
defaults:
  - override hydra/launcher: submitit_slurm

hydra:
  launcher:
    snapshot:
      enabled: true
      branch_prefix: "slurm-job"
      symlink_paths:
        - "outputs"
        - "multirun"
        - ".submitit"
      push_to_remote: true
```

### 5. `README.md` (MODIFIED)
Added comprehensive documentation covering:
- Feature overview and benefits
- How it works (step-by-step)
- Configuration options
- Usage examples
- Requirements
- Example scenario walkthrough

### 6. `test_snapshot.py` (NEW)
Test script to verify snapshot functionality:
- Test 1: Repository root detection
- Test 2: Snapshot branch creation
- Test 3: Worktree creation with symlinks

## How It Works

### Snapshot Creation Flow

```
1. User launches job with snapshot enabled
   ↓
2. Launcher checks hydra.launcher.snapshot.enabled
   ↓
3. Create snapshot branch: slurm-job-YYYYMMDD-HHMMSS
   - Uses temporary worktree to avoid affecting main repo
   - Copies ALL files (including untracked) via rsync
   - Commits changes to snapshot branch
   - Pushes to remote (optional)
   ↓
4. Create job worktree from snapshot branch
   - Clone snapshot branch to temporary directory
   - Create symlinks for output paths
   ↓
5. Change working directory to worktree
   ↓
6. Execute job (runs in snapshot, writes via symlinks)
   ↓
7. Restore working directory on completion
```

### Key Design Decisions

1. **Working Directory Patching**: Changed `os.chdir()` in `__call__` rather than modifying submitit parameters
   - Simpler implementation
   - Works with all submitit features
   - Transparent to user code

2. **Shared Snapshot Branch**: Single branch per launch, multiple worktrees per job
   - Efficient for array jobs
   - All jobs from same launch use same code snapshot
   - Each job still gets isolated filesystem view

3. **Symlink Strategy**: Output directories symlinked to original repo
   - Outputs stay organized in one location
   - No need to copy outputs after job completion
   - Works transparently with Hydra's output management

4. **Graceful Degradation**: Snapshot failures don't crash jobs
   - Try/except around snapshot creation
   - Fall back to normal execution if snapshot fails
   - Log errors for debugging

## Usage

### Basic Usage
```bash
# Enable snapshot in config
python my_app.py hydra.launcher.snapshot.enabled=true

# Run multi-job sweep with snapshots
python my_app.py -m param=1,2,3 hydra.launcher.snapshot.enabled=true
```

### Configuration Options
```yaml
hydra:
  launcher:
    snapshot:
      enabled: true                    # Enable/disable feature
      branch_prefix: "slurm-job"       # Prefix for branch names
      symlink_paths:                   # Paths to symlink
        - "outputs"
        - "multirun"
        - ".submitit"
      push_to_remote: true             # Push branches to remote
```

### Command-Line Overrides
```bash
# Disable snapshot
python my_app.py hydra.launcher.snapshot.enabled=false

# Custom branch prefix
python my_app.py hydra.launcher.snapshot.branch_prefix=experiment

# Custom symlink paths
python my_app.py 'hydra.launcher.snapshot.symlink_paths=[outputs,logs,data]'
```

## Testing

Run the test script to verify installation:
```bash
cd plugins/hydra_submitit_launcher
python test_snapshot.py
```

Expected output:
```
Testing Git Snapshot Functionality
==================================================

[Test 1] Getting repository root...
✓ Repository root found: /path/to/repo

[Test 2] Creating git snapshot...
✓ Created snapshot branch: test-snapshot-YYYYMMDD-HHMMSS
  Commit hash: abcd1234

[Test 3] Creating snapshot worktree...
✓ Created snapshot worktree: /tmp/hypersteer-job-xxxxx/code
✓ Worktree is valid git repository

==================================================
✓ All tests passed!
```

## Requirements

- Python 3.8+
- Git 2.5+ (for worktree support)
- rsync (for copying files with .gitignore respect)
- Git repository initialized in project
- Write access to repository (read-only repos will skip push)

## Benefits

1. **Code Isolation**: Continue working without affecting running jobs
2. **Reproducibility**: Each job's exact code tracked in git branch
3. **Output Organization**: All outputs in original directory despite snapshots
4. **Zero Code Changes**: Works with existing scripts
5. **Concurrent Jobs**: Multiple jobs with different code versions can run safely
6. **Optional**: Can be disabled per-job or per-run
7. **Robust**: Graceful fallback if snapshot creation fails

## Limitations

1. **Disk Space**: Each worktree is a full clone (~repo size per job)
2. **Git Required**: Only works in git repositories
3. **Branch Accumulation**: Snapshot branches accumulate (manual cleanup needed)
4. **First Launch Slower**: Snapshot creation adds ~5-10 seconds to launch

## Future Enhancements (Optional)

1. **Auto-cleanup**: Add option to automatically delete snapshot branches after job completion
2. **Shallow Clones**: Use `--depth 1` to reduce worktree disk usage
3. **Snapshot Sharing**: Reuse snapshots if code hasn't changed
4. **Status Tracking**: Add snapshot info to Hydra job metadata
5. **Cleanup Script**: Provide utility to clean up old snapshot branches
6. **Performance Metrics**: Log timing for snapshot operations

## Troubleshooting

### Snapshot creation fails
- **Cause**: Not in a git repository
- **Solution**: Initialize git: `git init`

### Push to remote fails
- **Cause**: No remote configured or no push access
- **Solution**: Warning logged, branch created locally only

### Symlinks not working
- **Cause**: Target directories don't exist in original repo
- **Solution**: Create directories before first run

### Disk space issues
- **Cause**: Many worktrees accumulating
- **Solution**: Clean up temp directories: `rm -rf /tmp/hypersteer-job-*`

### Branch accumulation
- **Cause**: Snapshot branches not cleaned up
- **Solution**: Delete old branches: `git branch | grep slurm-job | xargs git branch -D`

## Architecture Notes

The implementation follows Hydra's plugin architecture:
- Config defined in `config.py` using dataclasses
- Core logic in launcher's `__call__` method
- Git operations isolated in separate module
- Minimal changes to existing code
- Backward compatible (disabled by default)

The working directory patching approach was chosen because:
1. Submitit doesn't expose working directory parameter
2. Modifying `sys.path` would be fragile
3. Changing environment variables is unreliable
4. `os.chdir()` is simple and works universally
5. Cleanup in `finally` block ensures restoration

## Conclusion

The git snapshot feature is now fully integrated into the Hydra Submitit Launcher. It provides production-ready code isolation for SLURM jobs while maintaining backward compatibility and ease of use.
