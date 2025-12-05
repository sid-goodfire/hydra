# Hydra Submitit Launcher
Provides a [`Submitit`](https://github.com/facebookincubator/submitit) based Hydra Launcher supporting [SLURM ](https://slurm.schedmd.com/documentation.html).

See [website](https://hydra.cc/docs/plugins/submitit_launcher) for more information

## Git Snapshot Feature

The Submitit Launcher now includes an optional Git snapshot feature that creates isolated code snapshots for SLURM jobs. This allows you to:

- **Continue working** on your code without affecting running jobs
- **Track exact code state** for each job via git branches
- **Keep outputs organized** - all outputs stay in the original directory via symlinks
- **Run concurrent jobs safely** - each job gets its own isolated code snapshot

### How It Works

1. When a job is launched with snapshot enabled, the launcher creates a timestamped git branch containing the current code state
2. A separate worktree is created from this snapshot branch
3. Specified directories (outputs, logs, etc.) are symlinked back to the original repo
4. The job runs in the snapshot worktree but writes outputs to the original location
5. You can continue working in your original repo without affecting running jobs

### Configuration

Enable snapshots by adding the `snapshot` configuration to your Hydra launcher config:

```yaml
defaults:
  - override hydra/launcher: submitit_slurm

hydra:
  launcher:
    # Standard Slurm parameters
    timeout_min: 60
    cpus_per_task: 4

    # Git snapshot configuration
    snapshot:
      enabled: true                    # Enable/disable snapshot feature
      branch_prefix: "slurm-job"       # Prefix for snapshot branch names
      symlink_paths:                   # Directories to symlink to original repo
        - "outputs"
        - "multirun"
        - ".submitit"
      push_to_remote: true             # Push snapshot branches to remote (optional)
      worktree_dir: null               # Where to create worktrees (null = parent dir of repo)
```

### Configuration Options

**`enabled`** (bool, default: `false`)
- Enable or disable the snapshot feature

**`branch_prefix`** (str, default: `"slurm-job"`)
- Prefix for snapshot branch names (e.g., `slurm-job-20231201-120000`)

**`symlink_paths`** (list[str], default: `["outputs", "multirun", ".submitit"]`)
- Directories to symlink from snapshot back to original repo
- Outputs written to these paths appear in the original repo

**`push_to_remote`** (bool, default: `true`)
- Whether to push snapshot branches to remote (fails gracefully if no access)

**`worktree_dir`** (str | null, default: `null`)
- Base directory where snapshot worktrees are created
- If `null`: Creates in parent directory of repo (e.g., `/home/user/` if repo is `/home/user/myproject/`)
- If specified: Creates in that directory (e.g., `/tmp/snapshots`, `/scratch/$USER/jobs`)
- Useful for controlling disk usage or using faster filesystems

### Usage Example

```bash
# Run with snapshot enabled
python my_app.py -m task=1,2,3

# Disable snapshot for debugging
python my_app.py -m task=1,2,3 hydra.launcher.snapshot.enabled=false

# Customize symlink paths
python my_app.py -m task=1,2,3 'hydra.launcher.snapshot.symlink_paths=[outputs,logs,data]'

# Use specific directory for worktrees (e.g., fast local storage)
python my_app.py -m task=1,2,3 hydra.launcher.snapshot.worktree_dir=/tmp/my-snapshots

# Use cluster scratch space
python my_app.py -m task=1,2,3 'hydra.launcher.snapshot.worktree_dir=/scratch/$USER/hydra-jobs'
```

### Why Control Worktree Location?

The `worktree_dir` option is useful for:

1. **Fast Local Storage**: Use SSD/NVMe for faster git operations
   ```yaml
   worktree_dir: /local/scratch/snapshots
   ```

2. **Scratch Space**: Cluster scratch directories often have more space
   ```yaml
   worktree_dir: /scratch/$USER/hydra-jobs
   ```

3. **Disk Quotas**: Avoid filling up home directory quotas
   ```yaml
   worktree_dir: /data/$USER/tmp-jobs
   ```

4. **Cleanup**: Easier to clean up all snapshots in one location
   ```bash
   rm -rf /tmp/my-snapshots/*
   ```

**Default Behavior (when `null`):**
- If repo is `/home/user/myproject/`, creates in `/home/user/hydra-job-xxxxx/`
- Keeps snapshots close to original repo
- Works well for most cases

### Requirements

- Git repository initialized in your project
- `rsync` command available on the system
- Write access to git repository (optional: push access for remote branches)

### How Snapshots Are Created

1. **Snapshot Branch**: Creates a timestamped branch like `slurm-job-20231201-143022`
2. **Worktree**: Creates a temporary directory with the snapshot code
3. **Symlinks**: Creates symlinks for output directories pointing back to original repo
4. **Job Execution**: Job runs in snapshot directory, writes outputs via symlinks
5. **Branch Persistence**: Snapshot branches remain in your repo for reproducibility

### Benefits

- **Code Isolation**: Continue development without breaking running jobs
- **Reproducibility**: Each job's exact code is tracked in a git branch
- **Output Organization**: All outputs in one place despite code snapshots
- **Zero Code Changes**: Works with existing scripts without modification
- **Concurrent Jobs**: Multiple jobs can run from different snapshots safely

### Example Scenario

```
# Terminal 1: Launch a long-running job
$ python train.py experiment=baseline
# Creates snapshot branch: slurm-job-20231201-120000
# Job runs in snapshot worktree
# Outputs written to: outputs/2023-12-01/12-00-00/

# Terminal 1: Continue working immediately
$ git checkout -b feature/new-model
$ vim model.py  # Make changes without affecting running job

# Later: Launch another job with new changes
$ python train.py experiment=new_model
# Creates snapshot branch: slurm-job-20231201-140000
# Outputs written to: outputs/2023-12-01/14-00-00/
```

Both jobs run independently with their own code versions, but all outputs are in the same `outputs/` directory.