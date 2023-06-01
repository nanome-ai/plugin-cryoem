import enum
import logging
import random
from nanome._internal.network import Packet, Data


logger = logging.getLogger(__name__)


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


def random_request_id():
    """Generate a random but valid request id."""
    max_req_id = 4294967295
    request_id = random.randint(0, max_req_id)
    return request_id


def convert_bytes_to_packet(received_bytes):
    """Parse received bytes into Packet instance."""
    data = Data()
    data.received_data(received_bytes)
    packet = Packet()
    got_header = packet.get_header(data)
    got_payload = packet.get_payload(data)
    if not got_header:
        logger.warning("Could not get packet header")
    if not got_payload:
        logger.warning("Could not get packet payload")
    return packet
