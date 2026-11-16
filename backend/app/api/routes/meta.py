"""Supporting endpoint: the options and limits a client needs to build a query."""

from fastapi import APIRouter

from app.api.dependencies import MeasurementServiceDep, SettingsDep
from app.api.presenters import present_meta
from app.api.schemas import MetaResponse

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/meta", summary="Options and limits of this deployment")
def get_meta(settings: SettingsDep, service: MeasurementServiceDep) -> MetaResponse:
    """Aggregation levels with their maximum range, measurement types with their official labels
    and units, the time zones used, and whether the data is real or recorded (demo mode).

    Clients read these values here instead of copying them, because the maximum ranges can be
    changed through the configuration.
    """
    return present_meta(settings, service.source_label)
