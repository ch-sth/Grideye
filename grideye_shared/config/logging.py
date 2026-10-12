import logging
import os
import sys

from grideye_shared.config.files import read_config


def configure_logging(service: str) -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", read_config("system")["log_level"]),
        stream=sys.stdout,
        format=f'%(asctime)sZ level=%(levelname)s service={service} message="%(message)s"',
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )
