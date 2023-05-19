import os
import asyncio
import functools
import inspect
import json
import logging
import sys
from nanome._internal.network import Packet
from nanome.api.serializers import CommandMessageSerializer
from nanome_sdk.session.session_client import SessionClient

from nanome.api import control, ui
from nanome_sdk.plugin_2_0 import utils as server_utils

# Make sure plugin folder is in path
# Bold assumption that plugin is always in `plugin` folder
# in working directory
plugin_path = os.getcwd()  # Starting directory (/app)
sys.path.append(plugin_path)
from plugin import plugin_class

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(name="SessionInstance")

__all__ = ["start_session"]


async def start_session(plugin_instance, plugin_id, session_id, version_table):
    logger.info("Starting Session!")
    await plugin_instance.client.send_connect(plugin_id, session_id, version_table)
    await _start_session_loop(plugin_instance)


async def _start_session_loop(plugin_instance):
    await plugin_instance.on_start()
    reader = plugin_instance.client.reader
    tasks = []
    while True:
        logger.debug("Waiting for input...")
        received_bytes = await reader.readexactly(Packet.packet_header_length)
        unpacked = Packet.header_unpack(received_bytes)
        payload_length = unpacked[4]
        received_bytes += await reader.readexactly(payload_length)
        packet = server_utils.receive_bytes(received_bytes)
        task = await _route_incoming_payload(packet.payload, plugin_instance)
        if task:
            tasks.append(task)
        await asyncio.sleep(0.1)


async def _route_incoming_payload(payload, plugin_instance):
    logger.debug("Routing Payload")
    serializer = CommandMessageSerializer()
    received_obj_list, command_hash, request_id = serializer.deserialize_command(
        payload, plugin_instance.version_table)
    command = CommandMessageSerializer._commands[command_hash]
    logger.debug(f"Command: {command.name()}")
    logger.debug(f"Request ID: {request_id}")
    if request_id in plugin_instance.request_futs:
        fut = plugin_instance.request_futs[request_id]
        fut.set_result(received_obj_list)

    if isinstance(command, control.messages.Run):
        logger.info("on_run_called")
        task = asyncio.create_task(plugin_instance.on_run())
        return task
    elif isinstance(command, ui.messages.ButtonCallback):
        logger.info("Button Clicked.")
        # See if we have a registered callback for this button
        content_id, _ = received_obj_list
        menu_btn = None
        for btn in plugin_instance.client.callbacks:
            if btn._content_id == content_id:
                menu_btn = btn
                break
        if not menu_btn:
            logger.warning(f"No callback registered for button {content_id}")
            return
        # Call the callback
        callback_fn = btn._pressed_callback
        is_async_fn = inspect.iscoroutinefunction(callback_fn)
        is_async_partial = isinstance(callback_fn, functools.partial) and \
            inspect.iscoroutinefunction(callback_fn.func)

        if is_async_fn or is_async_partial:
            await callback_fn(menu_btn)
        else:
            callback_fn(menu_btn)


if __name__ == "__main__":
    plugin_id = int(sys.argv[1])
    session_id = int(sys.argv[2])
    plugin_class_filepath = sys.argv[3]
    version_table = json.loads(os.environ['NANOME_VERSION_TABLE'])
    logger.info(f"Running Session Loop! Plugin {plugin_id}, Session {session_id}")
    logger.info(f'Plugin Class {plugin_class.__name__}')
    plugin_instance = plugin_class()
    plugin_instance.plugin_id = plugin_id
    plugin_instance.session_id = session_id
    plugin_instance.version_table = version_table
    plugin_instance.client = SessionClient(plugin_id, session_id, version_table)
    session_coro = start_session(plugin_instance, plugin_id, session_id, version_table)
    loop = asyncio.get_event_loop()
    session_loop = loop.run_until_complete(session_coro)
