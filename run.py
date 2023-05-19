import asyncio
import os
from plugin import CryoEM
from nanome_sdk.server import Plugin_2_0


def main():
    plugin = Plugin_2_0()

    host = os.environ['NTS_HOST']
    port = int(os.environ['NTS_PORT'])
    name = "Cryo-EM"
    description = "Nanome plugin to load Cryo-EM maps and display them in Nanome as iso-surfaces"
    plugin_class = CryoEM
    asyncio.run(plugin.run(host, port, name, description, plugin_class))


if __name__ == "__main__":
    main()
