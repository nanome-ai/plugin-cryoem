import argparse
import asyncio
import os
import nanome

from nanome_sdk.plugin_server import PluginServer
from plugin import app


def create_parser():
    """Create command line parser For SpatialSequenceMatching Plugin.

    rtype: argsparser: args parser
    """
    parser = argparse.ArgumentParser(description='Parse Arguments to set up Sequence Matching Plugin and related Services.')
    plugin_group = parser.add_argument_group('Base Arguments')
    vault_group = parser.add_argument_group('Vault Arguments')

    # Add arguments from shared Plugin argparser, so that --help will show all possible arguments you can pass.
    base_parser = nanome.Plugin.create_parser()
    for action in base_parser._actions:
        if action.dest == 'help':
            continue
        plugin_group._add_action(action)

    # Add Sequence specific arguments
    vault_group.add_argument(
        '--vault-api-key',
        dest='vault_api_key',
        default=os.environ.get("VAULT_API_KEY", ""),
        help=argparse.SUPPRESS,
        required=False)
    vault_group.add_argument(
        '-u', '--url', '--vault-url',
        dest='vault_url',
        type=str,
        default=os.environ.get("VAULT_URL", None),
        help='Vault Web UI URL')
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    server = PluginServer()
    host = os.environ['NTS_HOST']
    port = int(os.environ['NTS_PORT'])
    name = "Cryo-EM"
    description = "Nanome plugin to load Cryo-EM maps and display them in Nanome as iso-surfaces"
    asyncio.run(server.run(host, port, name, description, app))


if __name__ == "__main__":
    main()
