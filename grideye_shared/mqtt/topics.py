from dataclasses import dataclass


@dataclass(frozen=True)
class Topics:
    uwb_position: str = "grideye/uwb/position"
    uwb_status: str = "grideye/uwb/status"
    flight_telemetry: str = "grideye/flight/telemetry"
    flight_attitude: str = "grideye/flight/attitude"
    flight_battery: str = "grideye/flight/battery"
    flight_mode: str = "grideye/flight/mode"
    flight_status: str = "grideye/flight/status"
    flight_command: str = "grideye/flight/command"
    flight_command_result: str = "grideye/flight/command/result"
    mission_command: str = "grideye/mission/command"
    mission_status: str = "grideye/mission/status"
    mission_progress: str = "grideye/mission/progress"
    mission_current_target: str = "grideye/mission/current_target"
    camera_status: str = "grideye/camera/status"
    ai_status: str = "grideye/ai/status"
    ai_detection: str = "grideye/ai/detection"
    grid_detection: str = "grideye/grid/detection"
    detection_confirmed: str = "grideye/detection/confirmed"
    service_status_wildcard: str = "grideye/system/services/+/status"
    system_events: str = "grideye/system/events"


TOPICS = Topics()


def service_status_topic(service: str) -> str:
    if not service or "/" in service or "+" in service or "#" in service:
        raise ValueError("invalid service name")
    return f"grideye/system/services/{service}/status"
