# MQTT policy

All topics are defined in `grideye_shared/mqtt/topics.py`. QoS 1 is used throughout:
delivery is important, duplicates are tolerated by correlation IDs and detection IDs, and QoS 2
would add unnecessary overhead on the Raspberry Pi. Status/current-value messages are retained.
Telemetry, commands, results, detections and system events are not retained.

Large image payloads never travel over MQTT; messages may contain an image reference instead.

