from fastapi import APIRouter, Depends, Query

from app.schemas.alert import AlertResponse, AlertScanResult, AlertSnooze
from app.services.alert_service import AlertService, get_alert_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    household_id: str = Query(...),
    severity: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
):
    return service.list(
        household_id=household_id,
        severity=severity,
        current_user=current_user,
    )


@router.patch("/{alert_id}/read", response_model=AlertResponse)
def read_alert(
    alert_id: str,
    current_user: dict = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
):
    return service.mark_read(alert_id=alert_id, current_user=current_user)


@router.post("/{alert_id}/snooze", response_model=AlertResponse)
def snooze_alert(
    alert_id: str,
    body: AlertSnooze = AlertSnooze(),
    current_user: dict = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
):
    return service.snooze(
        alert_id=alert_id,
        duration_hours=body.duration_hours,
        current_user=current_user,
    )


@router.post("/run-preview", response_model=AlertScanResult)
def run_preview(
    household_id: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
    service: AlertService = Depends(get_alert_service),
):
    return service.scan_and_generate(household_id=household_id, current_user=current_user)
