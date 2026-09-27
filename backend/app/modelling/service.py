from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.database.repositories.scenario_variants import ScenarioVariantRepository
from app.modelling.base import ModelAdapter
from app.modelling.delft3d.adapter import Delft3DAdapter
from app.modelling.auto_case import generate_delft3d_case, generate_dualsphysics_case
from app.modelling.runtime import SolverRuntimeDetector
from app.modelling.schemas import ModelPrepareRequest, SphExecutionDevice, Delft3DRunnerMode
from app.modelling.sph.adapter import DualSPHysicsAdapter
from app.schemas.scenarios import SimulationModel


class ModellingService:
    def __init__(self, *, delft3d_executable: str | None = None):
        self.variants = ScenarioVariantRepository()
        self._settings = get_settings()
        self.dual_sph_bin_dir = self._settings.dual_sph_bin_dir
        self.dual_sph_device = self._settings.dual_sph_device
        self.dual_sph_gpu_id = self._settings.dual_sph_gpu_id
        self.dual_sph_gencase = self._settings.dual_sph_gencase
        self.dual_sph_solver_gpu = self._settings.dual_sph_solver_gpu
        self.dual_sph_solver_cpu = self._settings.dual_sph_solver_cpu
        self.dual_sph_partvtk = self._settings.dual_sph_partvtk
        self.dual_sph_output_interval_s = self._settings.dual_sph_output_interval_s
        self.delft3d_executable = delft3d_executable or self._settings.delft3d_executable

    def runtime_status(self):
        # Settings are process-scoped and immutable for a running instance, while
        # device/binary availability can change, so detection itself is always fresh.
        return SolverRuntimeDetector(get_settings()).detect()

    def get_variant(self, db: Session, project_id: str, scenario_id: str, variant_id: str):
        variant = self.variants.get(db, variant_id)
        if variant is None or variant.base_scenario_id != scenario_id:
            raise NotFoundError("Scenario variant not found.")
        return variant

    def _adapter(self, model: SimulationModel, config: ModelPrepareRequest, *, sph_device: SphExecutionDevice | None = None, delft_mode: Delft3DRunnerMode | None = None, delft_executable: str | None = None) -> ModelAdapter:
        if model == SimulationModel.SPH:
            return DualSPHysicsAdapter(
                bin_dir=self.dual_sph_bin_dir,
                device=sph_device or config.sph_device,
                gpu_id=config.sph_gpu_id,
                gencase_executable=self.dual_sph_gencase,
                solver_gpu_executable=self.dual_sph_solver_gpu,
                solver_cpu_executable=self.dual_sph_solver_cpu,
                partvtk_executable=self.dual_sph_partvtk,
                output_interval_s=config.sph_output_interval_s,
                case_filename=config.sph_case_filename,
            )
        if model == SimulationModel.DELFT3D:
            return Delft3DAdapter(
                runner_mode=delft_mode or config.delft3d_runner_mode,
                executable=delft_executable or self.delft3d_executable,
            )
        raise ValueError("A concrete model adapter must be selected: sph or delft3d.")

    def prepare_variant(
        self,
        db: Session,
        *,
        project_id: str,
        scenario_id: str,
        variant_id: str,
        model: SimulationModel,
        config: ModelPrepareRequest,
    ):
        variant = self.get_variant(db, project_id, scenario_id, variant_id)
        if variant.model not in {model, SimulationModel.BOTH} and variant.model not in {model.value, SimulationModel.BOTH.value}:
            raise ValueError(f"Variant model '{variant.model}' does not support '{model.value}'.")

        runtime = self.runtime_status()
        runtime_warnings: list[str] = []
        effective_sph_device = config.sph_device
        effective_delft_mode = config.delft3d_runner_mode
        effective_delft_executable = config.solver_executable or self.delft3d_executable or None

        # Preparing model inputs is allowed even when the external solver runtime
        # is unavailable. This lets users inspect/download generated cases and
        # keeps solver availability enforcement at simulation-job submission time.
        # Actual execution is blocked by SimulationJobManager preflight.
        if model == SimulationModel.SPH:
            sph_runtime = runtime["sph"]
            if config.sph_device == SphExecutionDevice.GPU and sph_runtime.effective_device:
                effective_sph_device = SphExecutionDevice(sph_runtime.effective_device)
            runtime_warnings.extend(sph_runtime.warnings)

        if model == SimulationModel.DELFT3D:
            delft_runtime = runtime["delft3d"]
            if delft_runtime.ready:
                effective_delft_mode = Delft3DRunnerMode(
                    delft_runtime.runner_mode or Delft3DRunnerMode.DIMR.value
                )
                effective_delft_executable = str(delft_runtime.binaries["runner"])
                if config.delft3d_runner_mode != effective_delft_mode:
                    runtime_warnings.append(
                        f"Configured Delft3D runner '{config.delft3d_runner_mode.value}' is unavailable; using '{effective_delft_mode.value}'."
                    )
            else:
                runtime_warnings.extend(delft_runtime.warnings)

        adapter = self._adapter(
            model,
            config,
            sph_device=effective_sph_device,
            delft_mode=effective_delft_mode,
            delft_executable=effective_delft_executable,
        )
        preprocessing_artifacts = {
            "dem": config.preprocessed_dem,
            "river": config.prepared_river,
            "computational_domain": config.computational_domain,
            "domain_mask": config.domain_mask,
        }
        for label, value in preprocessing_artifacts.items():
            if value is not None and not Path(value).exists():
                raise ValueError(f"Preprocessing artifact '{label}' does not exist: {value}")
        if config.auto_generate:
            dem_path = preprocessing_artifacts.get("dem")
            if not dem_path:
                raise ValueError("Automatic model generation requires a preprocessed DEM.")
            if config.working_directory:
                native_dir = Path(config.working_directory).resolve() / "auto_native"
            else:
                native_dir = get_settings().model_work_dir / variant_id / model.value / "auto_native"
            if model == SimulationModel.SPH:
                generated = generate_dualsphysics_case(
                    variant_parameters=variant.parameters,
                    dem_path=Path(dem_path),
                    output_dir=native_dir,
                )
            else:
                generated = generate_delft3d_case(
                    variant_parameters=variant.parameters,
                    dem_path=Path(dem_path),
                    output_dir=native_dir,
                )
            native_dir = Path(generated["native_input_directory"])
        else:
            if not config.native_input_directory:
                raise ValueError("native_input_directory is required when auto_generate is false.")
            native_dir = Path(config.native_input_directory)
        workdir = (
            Path(config.working_directory)
            if config.working_directory
            else get_settings().model_work_dir / variant_id / model.value
        )
        prepared = adapter.prepare(
            variant_parameters=variant.parameters,
            native_input_directory=native_dir,
            working_directory=workdir,
            preprocessing_artifacts=preprocessing_artifacts,
        )
        from app.modelling.schemas import ModelPrepareResponse

        return ModelPrepareResponse(
            model=prepared.model,
            adapter_version=prepared.adapter_version,
            working_directory=str(prepared.working_directory.resolve()),
            manifest_path=str(prepared.manifest_path.resolve()),
            command=prepared.command,
            execution_steps=prepared.execution_steps,
            native_input_directory=str(native_dir.resolve()),
            warnings=[*runtime_warnings, *prepared.warnings],
        )
