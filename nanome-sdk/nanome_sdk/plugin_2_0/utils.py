import logging
from nanome._internal.network import Packet, Data

logger = logging.getLogger(__name__)


def receive_bytes(received_bytes):
    # Parse received bytes into Packet instance
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
