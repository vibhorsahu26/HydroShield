from pydantic import BaseModel, ConfigDict, Field


class AnalysisInputUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    simulation_job_id: str
    directory: str
    files: dict[str, str] = Field(default_factory=dict)
