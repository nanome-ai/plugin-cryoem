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
from plugin import plugin_class  # noqa: E402

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
    routing_tasks = []
    tasks = []
    while True:
        logger.debug("Waiting for input...")
        received_bytes = await reader.readexactly(Packet.packet_header_length)
        unpacked = Packet.header_unpack(received_bytes)
        payload_length = unpacked[4]
        received_bytes += await reader.readexactly(payload_length)
        packet = server_utils.receive_bytes(received_bytes)
        routing_task = asyncio.create_task(_route_incoming_payload(packet.payload, plugin_instance))
        routing_tasks.append(routing_task)
        for i in range(len(routing_tasks) - 1, -1, -1):
            routing_task = routing_tasks[i]
            if routing_task.done():
                result = routing_task.result()
                if result and inspect.iscoroutine(result):
                    tasks.append(result)
                del routing_tasks[i]
        await asyncio.sleep(0.1)


async def _route_incoming_payload(payload, plugin_instance):
    serializer = CommandMessageSerializer()
    received_obj_list, command_hash, request_id = serializer.deserialize_command(
        payload, plugin_instance.version_table)
    ui_callbacks = [ui.messages.ButtonCallback, ui.messages.SliderCallback]
    command = CommandMessageSerializer._commands[command_hash]
    logger.debug(f"Session Received command: {command.name()}, Request ID {request_id}")
    if request_id in plugin_instance.request_futs:
        # If this is a response to a request, set the future result
        try:
            fut = plugin_instance.request_futs[request_id]
        except KeyError:
            logger.warning(f"Could not find future for request_id {request_id}")
            return
        else:
            fut.set_result(received_obj_list)

    if isinstance(command, control.messages.Run):
        logger.info("on_run_called")
        task = asyncio.create_task(plugin_instance.on_run())
        return task
    elif type(command) in ui_callbacks:
        logger.info("UI Content Clicked.")
        # See if we have a registered callback for this button
        content_id, _ = received_obj_list
        menu_content = None
        for content in plugin_instance.client.callbacks:
            if content._content_id == content_id:
                menu_content = content
                break
        if not menu_content:
            logger.warning(f"No callback registered for button {content_id}")
            return
        # Call the callback
        if type(command) == ui.messages.ButtonCallback:
            callback_fn = menu_content._pressed_callback
        elif type(command) == ui.messages.SliderCallback:
            callback_fn = menu_content._changed_callback
        is_async_fn = inspect.iscoroutinefunction(callback_fn)
        is_async_partial = isinstance(callback_fn, functools.partial) and \
            inspect.iscoroutinefunction(callback_fn.func)

        if is_async_fn or is_async_partial:
            await callback_fn(menu_content)
        else:
            callback_fn(menu_content)


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
