# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from hydra.core.singleton import Singleton
from hydra.core.utils import (
    JobReturn,
    JobStatus,
    filter_overrides,
    run_job,
    setup_globals,
)
from hydra.plugins.launcher import Launcher
from hydra.types import HydraContext, TaskFunction
from omegaconf import DictConfig, OmegaConf, open_dict

from .config import BaseQueueConf
from .git_snapshot import create_git_snapshot, create_snapshot_worktree, get_repo_root

log = logging.getLogger(__name__)


class BaseSubmititLauncher(Launcher):
    _EXECUTOR = "abstract"

    def __init__(self, **params: Any) -> None:
        # Extract snapshot config separately before storing params
        snapshot_config = params.pop("snapshot", {})
        if OmegaConf.is_config(snapshot_config):
            snapshot_config = OmegaConf.to_container(snapshot_config, resolve=True)
        self.snapshot_config = snapshot_config

        # Store remaining params for submitit
        self.params = {}
        for k, v in params.items():
            if OmegaConf.is_config(v):
                v = OmegaConf.to_container(v, resolve=True)
            self.params[k] = v

        self.config: Optional[DictConfig] = None
        self.task_function: Optional[TaskFunction] = None
        self.sweep_configs: Optional[TaskFunction] = None
        self.hydra_context: Optional[HydraContext] = None

    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        self.config = config
        self.hydra_context = hydra_context
        self.task_function = task_function

    def __call__(
        self,
        sweep_overrides: List[str],
        job_dir_key: str,
        job_num: int,
        job_id: str,
        singleton_state: Dict[type, Singleton],
    ) -> JobReturn:
        # lazy import to ensure plugin discovery remains fast
        import submitit

        assert self.hydra_context is not None
        assert self.config is not None
        assert self.task_function is not None

        # Handle git snapshot if enabled
        original_cwd = None
        snapshot_workdir = None
        snapshot_enabled = self.snapshot_config.get("enabled", False)

        if snapshot_enabled:
            try:
                # Extract snapshot configuration
                branch_prefix = self.snapshot_config.get("branch_prefix", "slurm-job")
                symlink_paths = self.snapshot_config.get("symlink_paths", [])
                worktree_dir_str = self.snapshot_config.get("worktree_dir")
                worktree_dir = Path(worktree_dir_str) if worktree_dir_str else None

                # Get repo root
                repo_root = get_repo_root()

                # Create snapshot (only once per launch, not per job)
                # We'll check if snapshot info is already stored
                if not hasattr(self, "_snapshot_branch"):
                    log.info(f"Creating git snapshot for job {job_num}...")
                    self._snapshot_branch, self._snapshot_commit = create_git_snapshot(
                        branch_prefix, repo_root
                    )
                    log.info(
                        f"Created snapshot branch: {self._snapshot_branch} "
                        f"(commit: {self._snapshot_commit[:8]})"
                    )

                # Create worktree for this specific job
                log.info(f"Creating snapshot worktree for job {job_num}...")
                snapshot_workdir = create_snapshot_worktree(
                    self._snapshot_branch, symlink_paths, repo_root, worktree_dir
                )

                # Change to snapshot directory
                original_cwd = Path.cwd()
                os.chdir(snapshot_workdir)
                log.info(f"Changed working directory to snapshot: {snapshot_workdir}")

            except Exception as e:
                log.error(f"Failed to create snapshot: {e}")
                # Fall back to running without snapshot
                if original_cwd and snapshot_workdir:
                    try:
                        os.chdir(original_cwd)
                    except Exception:
                        pass

        try:
            Singleton.set_state(singleton_state)
            setup_globals()
            sweep_config = self.hydra_context.config_loader.load_sweep_config(
                self.config, sweep_overrides
            )

            with open_dict(sweep_config.hydra.job) as job:
                # Populate new job variables
                job.id = submitit.JobEnvironment().job_id  # type: ignore
                sweep_config.hydra.job.num = job_num

            result = run_job(
                hydra_context=self.hydra_context,
                task_function=self.task_function,
                config=sweep_config,
                job_dir_key=job_dir_key,
                job_subdir_key="hydra.sweep.subdir",
            )

            return result

        finally:
            # Restore original working directory
            if original_cwd is not None:
                try:
                    os.chdir(original_cwd)
                    log.debug(f"Restored working directory to: {original_cwd}")
                except Exception as e:
                    log.warning(f"Failed to restore working directory: {e}")

    def checkpoint(self, *args: Any, **kwargs: Any) -> Any:
        """Resubmit the current callable at its current state with the same initial arguments."""
        # lazy import to ensure plugin discovery remains fast
        import submitit

        return submitit.helpers.DelayedSubmission(self, *args, **kwargs)

    def launch(
        self, job_overrides: Sequence[Sequence[str]], initial_job_idx: int
    ) -> Sequence[JobReturn]:
        # lazy import to ensure plugin discovery remains fast
        import submitit

        assert self.config is not None

        num_jobs = len(job_overrides)
        assert num_jobs > 0
        params = self.params
        # build executor
        init_params = {"folder": self.params["submitit_folder"]}
        specific_init_keys = {"max_num_timeout"}

        init_params.update(
            **{
                f"{self._EXECUTOR}_{x}": y
                for x, y in params.items()
                if x in specific_init_keys
            }
        )
        init_keys = specific_init_keys | {"submitit_folder"}
        executor = submitit.AutoExecutor(cluster=self._EXECUTOR, **init_params)

        # specify resources/parameters
        baseparams = set(OmegaConf.structured(BaseQueueConf).keys())
        params = {
            x if x in baseparams else f"{self._EXECUTOR}_{x}": y
            for x, y in params.items()
            if x not in init_keys
        }
        executor.update_parameters(**params)

        log.info(
            f"Submitit '{self._EXECUTOR}' sweep output dir : "
            f"{self.config.hydra.sweep.dir}"
        )
        sweep_dir = Path(str(self.config.hydra.sweep.dir))
        sweep_dir.mkdir(parents=True, exist_ok=True)
        if "mode" in self.config.hydra.sweep:
            mode = int(str(self.config.hydra.sweep.mode), 8)
            os.chmod(sweep_dir, mode=mode)

        job_params: List[Any] = []
        for idx, overrides in enumerate(job_overrides):
            idx = initial_job_idx + idx
            lst = " ".join(filter_overrides(overrides))
            log.info(f"\t#{idx} : {lst}")
            job_params.append(
                (
                    list(overrides),
                    "hydra.sweep.dir",
                    idx,
                    f"job_id_for_{idx}",
                    Singleton.get_state(),
                )
            )

        jobs = executor.map_array(self, *zip(*job_params))
        job_ids = [j.job_id for j in jobs]
        log.info(f"Submitted {len(jobs)} jobs: {job_ids}")
        log.info("Jobs submitted asynchronously. Exiting without waiting for results.")
        return [
            JobReturn(overrides=list(overrides), status=JobStatus.UNKNOWN)
            for overrides in job_overrides
        ]


class LocalLauncher(BaseSubmititLauncher):
    _EXECUTOR = "local"


class SlurmLauncher(BaseSubmititLauncher):
    _EXECUTOR = "slurm"
