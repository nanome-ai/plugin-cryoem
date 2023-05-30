
import functools
import inspect
import logging

from nanome.api import ui
from collections import defaultdict

logger = logging.getLogger(__name__)


class UIManager:

    def __init__(self):
        self.callbacks = defaultdict(dict)
        self.menus = {}

    def register_btn_pressed_callback(self, btn: ui.Button, callback_fn):
        # hook_ui_callback = Messages.hook_ui_callback
        ui_hook = 'button_press'  # Not acutally enumerated anywhere
        content_id = btn._content_id
        self.callbacks[content_id][ui_hook] = callback_fn
        btn._pressed_callback = callback_fn

    def register_sld_changed_callback(self, sld: ui.Slider, callback_fn):
        ui_hook = 'sld_changed'  # Not acutally enumerated anywhere
        content_id = sld._content_id
        self.callbacks[content_id][ui_hook] = callback_fn
        sld._changed_callback = callback_fn

    async def handle_ui_command(self, command, received_obj_list):
        content_id, _ = received_obj_list
        menu_content = None
        for content in self.callbacks:
            if content._content_id == content_id:
                menu_content = content
                break
        if not menu_content:
            logger.warning(f"No callback registered for button {content_id}")
            return
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
