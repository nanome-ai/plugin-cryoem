import requests


class VaultManager:
    def __init__(self, api_key, server_url):
        self.api_key = api_key
        if server_url.endswith('/'):
            server_url = server_url[:-1]
        self.server_url = server_url

    def command(self, command, path, data=None, files=None):
        headers = {}
        if self.api_key:
            headers['vault-api-key'] = self.api_key
        if data is None:
            data = {}
        data['command'] = command
        url = self.server_url + '/files/' + path
        return requests.post(url, headers=headers, data=data, files=files)

    def get(self, path, key):
        headers = {}
        if self.api_key:
            headers['vault-api-key'] = self.api_key
        if key:
            headers['vault-key'] = key
        url = self.server_url + '/files/' + (path or '')
        return requests.get(url, headers=headers)

    # decrypts full contents of path, return False if key invalid
    def decrypt_folder(self, path, key):
        return self.command('decrypt', path, {'key': key})

    # get supported file extensions
    def get_extensions(self):
        url = f'{self.server_url}/info'
        r = requests.get(url)
        return r.json()['extensions']

    # write decrypted file to out_put
    def get_file(self, path, key, out_path):
        r = self.get(path, key)
        if not r.ok:
            return False
        with open(out_path, 'wb') as f:
            f.write(r.content)
        return True

    # check if key is correct to decrypt
    def is_key_valid(self, path, key):
        r = self.command('verify', path, {'key': key})
        return r.json()['success']

    # list files, folders, and locked folders in path
    def list_path(self, path=None, key=None):
        r = self.get(path, key)
        return r.json()
