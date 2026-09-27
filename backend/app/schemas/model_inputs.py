from pydantic import BaseModel, ConfigDict, Field


class ModelInputUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    model: str
    filename: str = Field(min_length=1)
    native_input_directory: str
    files: list[str] = Field(default_factory=list)
