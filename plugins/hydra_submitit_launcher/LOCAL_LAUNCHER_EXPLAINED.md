# How Submitit Local Launcher Works

## Overview

The `LocalLauncher` is one of two launchers provided by the Hydra Submitit plugin (the other being `SlurmLauncher`). Both inherit from `BaseSubmititLauncher` and differ only in the `_EXECUTOR` type they use.

## Class Hierarchy

```python
class BaseSubmititLauncher(Launcher):
    _EXECUTOR = "abstract"  # Base class

class LocalLauncher(BaseSubmititLauncher):
    _EXECUTOR = "local"     # Runs jobs locally with multiprocessing

class SlurmLauncher(BaseSubmititLauncher):
    _EXECUTOR = "slurm"     # Submits jobs to SLURM cluster
```

## How It Works

### 1. **Initialization** (`__init__`)

When you configure `hydra/launcher: submitit_local`, Hydra instantiates `LocalLauncher` with config parameters:

```python
launcher = LocalLauncher(
    submitit_folder="${hydra.sweep.dir}/.submitit/%j",
    timeout_min=60,
    cpus_per_task=4,
    # ... other params
)
```

These parameters are stored in `self.params` as a dictionary.

### 2. **Launch** (`launch` method)

When you run a multi-run sweep with `-m`, Hydra calls `launcher.launch()`:

```python
def launch(self, job_overrides: Sequence[Sequence[str]], initial_job_idx: int):
    # 1. Create submitit executor
    executor = submitit.AutoExecutor(cluster="local", folder=self.params["submitit_folder"])

    # 2. Configure executor with parameters
    executor.update_parameters(
        timeout_min=60,
        cpus_per_task=4,
        # ...
    )

    # 3. Build job parameters for each configuration
    job_params = []
    for idx, overrides in enumerate(job_overrides):
        job_params.append((
            list(overrides),           # e.g., ["param=1"]
            "hydra.sweep.dir",         # job_dir_key
            idx,                       # job_num
            f"job_id_for_{idx}",       # job_id
            Singleton.get_state(),     # singleton state
        ))

    # 4. Submit all jobs as array
    jobs = executor.map_array(self, *zip(*job_params))

    # 5. Return immediately (async execution)
    return [JobReturn(status=JobStatus.UNKNOWN) for _ in job_overrides]
```

### 3. **Job Execution** (`__call__` method)

Each job runs in a **separate process** and calls the launcher instance's `__call__` method:

```python
def __call__(
    self,
    sweep_overrides: List[str],  # e.g., ["param=1"]
    job_dir_key: str,            # "hydra.sweep.dir"
    job_num: int,                # 0, 1, 2, ...
    job_id: str,                 # "job_id_for_0"
    singleton_state: Dict,       # Hydra state
) -> JobReturn:
    # 1. Restore Hydra state
    Singleton.set_state(singleton_state)
    setup_globals()

    # 2. Load configuration with overrides
    sweep_config = self.hydra_context.config_loader.load_sweep_config(
        self.config, sweep_overrides
    )

    # 3. Set job metadata
    sweep_config.hydra.job.id = submitit.JobEnvironment().job_id
    sweep_config.hydra.job.num = job_num

    # 4. Run the actual job function
    return run_job(
        hydra_context=self.hydra_context,
        task_function=self.task_function,  # Your @hydra.main function
        config=sweep_config,
        job_dir_key=job_dir_key,
        job_subdir_key="hydra.sweep.subdir",
    )
```

## Key Differences: Local vs Slurm

| Aspect | LocalLauncher | SlurmLauncher |
|--------|--------------|---------------|
| **Execution** | Spawns local processes | Submits to SLURM queue |
| **Parallelism** | Limited by local CPUs | Cluster-wide parallelism |
| **Environment** | Same machine | Potentially different nodes |
| **Job Submission** | Immediate execution | Queued, scheduled later |
| **Working Directory** | Same as launch dir | Same as launch dir* |

*With our snapshot feature, the working directory can be changed to a snapshot!

## Under the Hood: Submitit Local Executor

When you use `cluster="local"`, submitit:

1. **Pickles** the callable (the launcher instance) and parameters
2. **Creates** a bash script that:
   - Unpickles the callable and parameters
   - Calls the callable with the parameters
   - Pickles the result
3. **Spawns** a subprocess to run the bash script
4. **Monitors** the process with timeout
5. **Returns** a Job object that can be queried for status/results

### File Structure

After running a local job array, you'll see:

```
.submitit/
├── 1234/
│   ├── 1234_0_log.out           # stdout for job 0
│   ├── 1234_0_log.err           # stderr for job 0
│   ├── 1234_0_submitted.pkl     # pickled callable + params
│   ├── 1234_0_result.pkl        # pickled result
│   ├── 1234_1_log.out           # stdout for job 1
│   ├── 1234_1_log.err           # stderr for job 1
│   └── ...
└── 1234_submission.sh           # bash script to run jobs
```

## Execution Flow Diagram

```
User runs: python my_app.py -m param=1,2,3
│
├─> Hydra calls launcher.launch(job_overrides=[["param=1"], ["param=2"], ["param=3"]])
│   │
│   ├─> Creates submitit.AutoExecutor(cluster="local")
│   │
│   ├─> executor.map_array(launcher_instance, job_params)
│   │   │
│   │   ├─> Pickles launcher_instance and params for each job
│   │   │
│   │   ├─> Spawns 3 separate processes:
│   │   │   │
│   │   │   ├─> Process 1: launcher("param=1", ...) → __call__
│   │   │   │   └─> run_job() → YOUR FUNCTION(config)
│   │   │   │
│   │   │   ├─> Process 2: launcher("param=2", ...) → __call__
│   │   │   │   └─> run_job() → YOUR FUNCTION(config)
│   │   │   │
│   │   │   └─> Process 3: launcher("param=3", ...) → __call__
│   │   │       └─> run_job() → YOUR FUNCTION(config)
│   │   │
│   │   └─> Returns list of Job objects
│   │
│   └─> launch() returns immediately (async)
│
└─> Main process exits (jobs continue in background)
```

## Why This Matters for Snapshot Feature

Understanding this flow is crucial for the snapshot feature:

### The Challenge

Each job runs in a **separate process** spawned by submitit. The `__call__` method is executed in that child process, not the main process.

### The Solution

We modify `__call__` to change the working directory **in the child process**:

```python
def __call__(self, ...):
    original_cwd = Path.cwd()

    if snapshot_enabled:
        # Create snapshot worktree
        snapshot_workdir = create_snapshot_worktree(...)

        # Change working directory IN THIS PROCESS
        os.chdir(snapshot_workdir)

    try:
        # Job runs with changed working directory
        result = run_job(...)
        return result
    finally:
        # Restore working directory
        if original_cwd:
            os.chdir(original_cwd)
```

### Why This Works

1. Each job is in its **own process** with its own working directory
2. Changing `os.chdir()` only affects **that process**
3. Other jobs and the main process are **unaffected**
4. The worktree is **isolated** per job
5. Symlinks ensure **outputs go to original location**

## Local vs Slurm: Snapshot Behavior

### Local Launcher

```
Main Process (current directory: /repo)
│
├─> Spawn Job 1 Process
│   └─> os.chdir(/tmp/snapshot-1/code)
│   └─> run_job() → outputs written via symlinks to /repo/outputs/
│
├─> Spawn Job 2 Process
│   └─> os.chdir(/tmp/snapshot-2/code)
│   └─> run_job() → outputs written via symlinks to /repo/outputs/
│
└─> Main process still in /repo
```

### Slurm Launcher

```
Login Node (submit from /repo)
│
├─> Submit Job 1 to SLURM
│   └─> Runs on compute node
│   └─> os.chdir(/tmp/snapshot-1/code) in SLURM job
│   └─> run_job() → outputs via symlinks to /repo/outputs/
│
├─> Submit Job 2 to SLURM
│   └─> Runs on compute node (maybe different one)
│   └─> os.chdir(/tmp/snapshot-2/code) in SLURM job
│   └─> run_job() → outputs via symlinks to /repo/outputs/
│
└─> Login node still in /repo
```

## Testing Local Launcher with Snapshot

Create a simple test app:

```python
# test_local_snapshot.py
import hydra
from omegaconf import DictConfig
import os
from pathlib import Path

@hydra.main(version_base=None, config_path=".", config_name="config")
def my_app(cfg: DictConfig) -> None:
    print(f"Task: {cfg.task}")
    print(f"Working directory: {Path.cwd()}")
    print(f"Output will be written to: {cfg.get('output_path', 'default')}")

    # Write a test file
    with open("test_output.txt", "w") as f:
        f.write(f"Task {cfg.task} completed\n")

if __name__ == "__main__":
    my_app()
```

```yaml
# config.yaml
defaults:
  - override hydra/launcher: submitit_local

task: 1

hydra:
  launcher:
    snapshot:
      enabled: true
      symlink_paths: [outputs, multirun]
```

Run it:
```bash
python test_local_snapshot.py -m task=1,2,3
```

You'll see:
- Each job runs in a different `/tmp/hypersteer-job-*/code` directory
- Outputs appear in your original `outputs/` directory
- Snapshot branches created in git

## Summary

**LocalLauncher:**
- Uses `submitit.AutoExecutor(cluster="local")`
- Spawns local processes for each job
- Each process calls `launcher.__call__()`
- Working directory can be changed per-process
- Perfect for testing snapshot feature locally before SLURM

**How Snapshot Integrates:**
- `__call__` runs in child process
- `os.chdir()` changes that process's directory
- Symlinks ensure outputs reach original location
- Same mechanism works for both Local and Slurm launchers

The beauty of the design is that **the same code works for both local and SLURM** because both use submitit's executor pattern and both call `__call__` in a separate execution context (process or SLURM job).
