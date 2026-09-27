from app.core.config import Settings
from app.modelling.schemas import ExecutionMode, ModelPrepareRequest


def test_model_prepare_defaults_to_automatic_mode():
    payload = ModelPrepareRequest()
    assert payload.execution_mode is None


def test_model_prepare_accepts_native_mode():
    payload = ModelPrepareRequest(execution_mode="native")
    assert payload.execution_mode == ExecutionMode.NATIVE


def test_model_prepare_accepts_prototype_mode():
    payload = ModelPrepareRequest(execution_mode="prototype")
    assert payload.execution_mode == ExecutionMode.PROTOTYPE


def test_demo_mode_setting_is_available():
    assert Settings(demo_mode=True).demo_mode is True
