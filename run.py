import asyncio
import os
from plugin import CryoEM
from nanome_sdk.plugin_server import PluginServer


def main():
    server = PluginServer()
    host = os.environ['NTS_HOST']
    port = int(os.environ['NTS_PORT'])
    name = "Cryo-EM"
    description = "Nanome plugin to load Cryo-EM maps and display them in Nanome as iso-surfaces"
    plugin_class = CryoEM
    asyncio.run(server.run(host, port, name, description, plugin_class))


if __name__ == "__main__":
    main()
