import json
import logging
import os
from collections.abc import Callable

import paho.mqtt.client as mqtt
from pydantic import BaseModel

MessageHandler = Callable[[str, bytes], None]


class MqttServiceClient:
    """Small MQTT v5 wrapper. Current state is retained; event streams are not."""

    def __init__(self, service: str, handler: MessageHandler | None = None) -> None:
        self.log = logging.getLogger(service)
        self.handler = handler
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=service)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.subscriptions: list[tuple[str, int]] = []

    def connect(self) -> None:
        self.client.connect(os.getenv("MQTT_HOST", "mqtt"), int(os.getenv("MQTT_PORT", "1883")))
        self.client.loop_start()

    def disconnect(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()

    def subscribe(self, topic: str, qos: int = 1) -> None:
        self.subscriptions.append((topic, qos))
        if self.client.is_connected():
            self.client.subscribe(topic, qos=qos)

    def publish(
        self, topic: str, payload: BaseModel | dict[str, object], *, retain: bool = False
    ) -> None:
        body = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        self.client.publish(topic, json.dumps(body), qos=1, retain=retain)

    def _on_connect(
        self, client: mqtt.Client, _userdata: object, _flags: object, reason: object, _props: object
    ) -> None:
        self.log.info("mqtt connected: %s", reason)
        for topic, qos in self.subscriptions:
            client.subscribe(topic, qos=qos)

    def _on_message(
        self, _client: mqtt.Client, _userdata: object, message: mqtt.MQTTMessage
    ) -> None:
        if self.handler:
            self.handler(message.topic, message.payload)
