from datetime import date
import pytest
from pydantic import ValidationError
from app.schemas.satellite import SatelliteValidationRequest


def test_end_date_must_be_later():
    with pytest.raises(ValidationError):
        SatelliteValidationRequest(analysis_result_id='a', start_date=date(2026,1,2), end_date=date(2026,1,2))
