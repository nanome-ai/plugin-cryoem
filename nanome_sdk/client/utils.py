import enum
import logging
import random


class PacketTypes(enum.IntEnum):
    plugin_list = 0
    plugin_connection = 1
    client_connection = 2
    message_to_plugin = 3
    message_to_client = 4
    plugin_disconnection = 5
    client_disconnection = 6
    master_change = 7
    keep_alive = 8
    logs_request = 9
    live_logs = 10


KEEP_ALIVE_TIME_INTERVAL = 60.0
KEEP_ALIVE_TIMEOUT = 15.0
PACKET_SIZE = 4096


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def get_env_data_as_dict(path: str) -> dict:
    with open(path, 'r') as f:
        return dict(
            tuple(line.replace('\n', '').split('=')) for line
            in f.readlines() if not line.startswith('#')
        )


def random_request_id():
    max_req_id = 4294967295
    request_id = random.randint(0, max_req_id)
    return request_id
