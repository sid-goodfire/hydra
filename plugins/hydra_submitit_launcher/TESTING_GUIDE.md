# Testing the Git Snapshot Feature

This guide shows you how to test the git snapshot functionality with the example app.

## Quick Test with Local Launcher

The easiest way to test is using the local launcher (no SLURM required):

### 1. Setup

First, make sure you're in a git repository:

```bash
cd /path/to/hydra/plugins/hydra_submitit_launcher/example
git status  # Should show you're in a repo
```

### 2. Run Single Job (No Snapshot)

Test the app works without snapshot:

```bash
python my_app.py
```

Expected output:
```
[HYDRA] Process ID 12345 executing task 1, with <JobEnvironment: ...>
```

### 3. Run with Snapshot (Single Job)

Run with snapshot enabled:

```bash
python my_app.py --config-name=config_local_snapshot
```

What to observe:
- Logs showing snapshot creation
- Worktree created in `/tmp/hydra-snapshots/`
- Job runs successfully
- Output appears in `outputs/` directory

### 4. Run Multi-Job Sweep with Snapshot

This is where snapshots really shine:

```bash
python my_app.py --config-name=config_local_snapshot -m task=1,2,3
```

What happens:
1. **Snapshot created once**: Branch like `local-test-20231201-120000`
2. **Three worktrees created**: One for each job
3. **Jobs run in parallel**: Each in its own isolated worktree
4. **Outputs collected**: All outputs in `multirun/YYYY-MM-DD/HH-MM-SS/`

Check the logs:
```bash
# View .submitit logs
ls -la multirun/*/.submitit/

# Check worktrees were created
ls -la /tmp/hydra-snapshots/

# Verify git branch was created
git branch | grep local-test
```

### 5. Test Different Worktree Locations

#### Default Location (Parent of Repo)

```bash
python my_app.py --config-name=config_local_snapshot -m task=1,2,3 \
    hydra.launcher.snapshot.worktree_dir=null
```

Worktrees created in parent directory of your repo.

#### Custom Location

```bash
# Use /tmp
python my_app.py --config-name=config_local_snapshot -m task=1,2,3 \
    hydra.launcher.snapshot.worktree_dir=/tmp/my-test

# Use current directory
python my_app.py --config-name=config_local_snapshot -m task=1,2,3 \
    hydra.launcher.snapshot.worktree_dir=$PWD/snapshots
```

#### Check Where Worktrees Were Created

```bash
# After running, check the logs for "Created snapshot worktree"
grep "Created snapshot worktree" multirun/*/.submitit/*/0_log.out
```

### 6. Verify Isolation

Open two terminals to see isolation in action:

**Terminal 1: Launch job with snapshot**
```bash
cd /path/to/hydra/plugins/hydra_submitit_launcher/example

# Launch a job that sleeps (modify my_app.py to sleep longer if needed)
python my_app.py --config-name=config_local_snapshot -m task=1,2,3
```

**Terminal 2: Make changes while job runs**
```bash
cd /path/to/hydra/plugins/hydra_submitit_launcher/example

# Make some changes to my_app.py
echo "# Test change" >> my_app.py

# Check git status
git status

# The running jobs are NOT affected by these changes!
```

**Terminal 2: Check snapshot branch**
```bash
# List snapshot branches
git branch | grep local-test

# See what's in the snapshot
git show local-test-YYYYMMDD-HHMMSS:my_app.py
```

## Advanced Testing

### Test Symlinks Work

Verify that outputs actually appear in original directory:

```bash
# Run job with snapshot
python my_app.py --config-name=config_local_snapshot -m task=1,2,3

# Check outputs exist in original location
ls -la outputs/
ls -la multirun/

# Verify jobs ran in snapshot directories (check logs)
grep "Working directory" multirun/*/.submitit/*/0_log.out
```

### Test Error Handling

#### Snapshot Disabled

```bash
python my_app.py --config-name=config_local_snapshot -m task=1,2,3 \
    hydra.launcher.snapshot.enabled=false
```

Should run normally without snapshots.

#### Invalid Worktree Directory

```bash
# Try a directory that doesn't exist and can't be created
python my_app.py --config-name=config_local_snapshot -m task=1,2,3 \
    hydra.launcher.snapshot.worktree_dir=/root/no-access
```

Should fall back gracefully or show error.

#### Not in Git Repo

```bash
# Copy example to non-git directory
mkdir /tmp/test-no-git
cp my_app.py config_local_snapshot.yaml /tmp/test-no-git/
cd /tmp/test-no-git

# Try to run with snapshot
python my_app.py --config-name=config_local_snapshot
```

Should show error about not being in git repo.

## Testing with SLURM (If Available)

If you have access to a SLURM cluster:

### 1. Create SLURM Config

```yaml
# config_slurm_snapshot.yaml
defaults:
  - override hydra/launcher: submitit_slurm

task: 1

hydra:
  launcher:
    timeout_min: 10
    cpus_per_task: 1
    partition: your_partition  # Change this!

    snapshot:
      enabled: true
      branch_prefix: "slurm-test"
      symlink_paths: [outputs, multirun, .submitit]
      push_to_remote: true
      worktree_dir: /scratch/$USER/hydra-jobs  # Use cluster scratch
```

### 2. Submit Jobs

```bash
python my_app.py --config-name=config_slurm_snapshot -m task=1,2,3
```

### 3. Monitor Jobs

```bash
# Check SLURM queue
squeue -u $USER

# Check job output
tail -f multirun/*/.submitit/*/0_log.out

# Check where worktree was created
squeue -u $USER -o "%.18i %.8u %.10a %.20j %.8T %N"
ssh <node> ls -la /scratch/$USER/hydra-jobs/
```

## Cleanup After Testing

### Remove Snapshot Branches

```bash
# List snapshot branches
git branch | grep -E "(local-test|slurm-test)"

# Delete them
git branch | grep -E "(local-test|slurm-test)" | xargs git branch -D
```

### Remove Worktree Directories

```bash
# Default location (parent of repo)
rm -rf /mnt/polished-lake/home/sbaskaran/code/hydra-job-*/

# Custom locations
rm -rf /tmp/hydra-snapshots/
rm -rf /tmp/my-test/
rm -rf /scratch/$USER/hydra-jobs/  # If using SLURM
```

### Clean Output Directories

```bash
cd /path/to/hydra/plugins/hydra_submitit_launcher/example
rm -rf outputs/ multirun/
```

## Expected Directory Structure After Testing

```
example/
├── my_app.py
├── config.yaml
├── config_local_snapshot.yaml
├── config_snapshot.yaml
├── outputs/                          # Single job outputs
│   └── YYYY-MM-DD/
│       └── HH-MM-SS/
│           ├── .hydra/
│           └── my_app.log
└── multirun/                         # Multi-job sweep outputs
    └── YYYY-MM-DD/
        └── HH-MM-SS/
            ├── .submitit/
            │   └── 12345/            # Job array ID
            │       ├── 12345_0_log.out
            │       ├── 12345_0_log.err
            │       ├── 12345_1_log.out
            │       └── ...
            ├── 0/                    # Job 0 outputs
            │   └── .hydra/
            ├── 1/                    # Job 1 outputs
            │   └── .hydra/
            └── 2/                    # Job 2 outputs
                └── .hydra/
```

Snapshot worktrees (temporary):
```
/tmp/hydra-snapshots/
├── hydra-job-abc123/
│   └── code/                         # Job 0 worktree
│       ├── my_app.py
│       ├── config.yaml
│       ├── outputs -> /path/to/original/outputs  (symlink)
│       └── multirun -> /path/to/original/multirun  (symlink)
├── hydra-job-def456/
│   └── code/                         # Job 1 worktree
└── hydra-job-ghi789/
    └── code/                         # Job 2 worktree
```

## Troubleshooting

### "Not in a git repository"

**Problem**: Error says not in git repo

**Solution**:
```bash
cd /path/to/hydra/plugins/hydra_submitit_launcher/example
git status  # Check you're in repo
```

The example directory is part of the Hydra repo, so this should work.

### "Failed to create snapshot"

**Problem**: Snapshot creation fails

**Check**:
```bash
# Verify git is working
git status
git log

# Check for uncommitted changes (OK, they'll be included)
git diff
```

### "Permission denied" for worktree_dir

**Problem**: Can't create worktree in specified directory

**Solution**: Use a directory you have write access to:
```bash
# Use /tmp (always works)
python my_app.py --config-name=config_local_snapshot \
    hydra.launcher.snapshot.worktree_dir=/tmp/test

# Or use $HOME
python my_app.py --config-name=config_local_snapshot \
    hydra.launcher.snapshot.worktree_dir=$HOME/snapshots
```

### Jobs not running

**Problem**: Jobs submitted but don't execute

**Check**:
```bash
# Check for errors in logs
cat multirun/*/.submitit/*/0_log.err

# Check if jobs are queued (local launcher)
ps aux | grep python

# Check job status
ls -la multirun/*/.submitit/
```

## Verification Checklist

After running tests, verify:

- [ ] Snapshot branch was created (`git branch | grep local-test`)
- [ ] Worktree directories were created in specified location
- [ ] Jobs completed successfully (check exit codes in logs)
- [ ] Outputs appeared in original `outputs/` or `multirun/` directory
- [ ] Symlinks worked (outputs not in worktree directory)
- [ ] Multiple jobs ran in parallel (check timestamps in logs)
- [ ] Each job had its own worktree (different paths in logs)
- [ ] Can make changes to code while jobs run without affecting them

## Quick Test Script

Copy and paste this to run all tests:

```bash
#!/bin/bash
set -e

cd /path/to/hydra/plugins/hydra_submitit_launcher/example

echo "Test 1: Single job without snapshot"
python my_app.py
echo "✓ Test 1 passed"

echo ""
echo "Test 2: Single job with snapshot"
python my_app.py --config-name=config_local_snapshot
echo "✓ Test 2 passed"

echo ""
echo "Test 3: Multi-job with snapshot (default location)"
python my_app.py --config-name=config_local_snapshot -m task=1,2,3 \
    hydra.launcher.snapshot.worktree_dir=null
echo "✓ Test 3 passed"

echo ""
echo "Test 4: Multi-job with snapshot (custom location)"
python my_app.py --config-name=config_local_snapshot -m task=1,2,3 \
    hydra.launcher.snapshot.worktree_dir=/tmp/test-snapshots
echo "✓ Test 4 passed"

echo ""
echo "All tests passed! 🎉"
echo ""
echo "Cleanup commands:"
echo "  git branch | grep local-test | xargs git branch -D"
echo "  rm -rf /tmp/hydra-snapshots/ /tmp/test-snapshots/"
echo "  rm -rf outputs/ multirun/"
```

Save as `run_tests.sh` and execute:
```bash
chmod +x run_tests.sh
./run_tests.sh
```
