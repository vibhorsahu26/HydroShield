from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.database.models import Scenario
from app.database.repositories.scenario_variants import ScenarioVariantRepository
from app.database.repositories.scenarios import ScenarioRepository
from app.schemas.scenario_generation import ScenarioGenerationConfig, ScenarioGenerationResponse
from app.schemas.scenarios import ScenarioConfig
from app.scenarios.generator import GENERATOR_VERSION, generate_scenario_variants


class ScenarioService:
    def __init__(self):
        self.scenarios = ScenarioRepository()
        self.variants = ScenarioVariantRepository()

    def get_for_project(self, db: Session, project_id: str, scenario_id: str) -> Scenario:
        scenario = self.scenarios.get(db, scenario_id)
        if scenario is None or scenario.project_id != project_id:
            raise NotFoundError("Scenario not found for project.")
        return scenario

    def generate_variants(
        self,
        db: Session,
        *,
        project_id: str,
        scenario_id: str,
        config: ScenarioGenerationConfig,
    ) -> ScenarioGenerationResponse:
        scenario = self.get_for_project(db, project_id, scenario_id)
        base = ScenarioConfig.model_validate(scenario.config)
        variants = generate_scenario_variants(base, config)

        existing = {item.code for item in self.variants.list_for_scenario(db, scenario_id)}
        conflicts = [item.code for item in variants if item.code in existing]
        if conflicts:
            raise ConflictError(
                "Scenario variants already exist: " + ", ".join(conflicts)
            )

        for variant in variants:
            self.variants.create(
                db,
                base_scenario_id=scenario_id,
                code=variant.code,
                kind=variant.kind.value,
                preset=variant.preset,
                breach_fraction=variant.breach_fraction,
                model=variant.model.value,
                parameters=variant.parameters,
                assumptions=variant.assumptions,
            )

        return ScenarioGenerationResponse(
            base_scenario_id=scenario_id,
            generator_version=GENERATOR_VERSION,
            variants=variants,
        )

    def list_variants(self, db: Session, *, project_id: str, scenario_id: str):
        self.get_for_project(db, project_id, scenario_id)
        return self.variants.list_for_scenario(db, scenario_id)
