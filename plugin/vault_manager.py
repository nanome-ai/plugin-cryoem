import requests


class VaultManager:

    def __init__(self, api_key, server_url):
        self.api_key = api_key
        if server_url.endswith('/'):
            server_url = server_url[:-1]
        self.server_url = server_url

    # add data to vault at path/filename, where filename can contain a path
    def add_file(self, path, filename, data, key=None):
        return self._command('upload', path, {'key': key}, {'files': (filename, data)})

    # creates a path and returns True. returns False if path exists
    def create_path(self, path, key=None):
        return self._command('create', path, {'key': key})

    # decrypts full contents of path, return False if key invalid
    def decrypt_folder(self, path, key):
        return self._command('decrypt', path, {'key': key})

    # get supported file extensions
    def get_extensions(self):
        url = f'{self.server_url}/info'
        r = requests.get(url)
        return r.json()['extensions']

    # write decrypted file to out_put
    def get_file(self, path, key, out_path):
        response = self.get(path, key)
        if not response.ok:
            return False
        with open(out_path, 'wb') as f:
            f.write(response.content)
        return True

    # check if key is correct to decrypt
    def is_key_valid(self, path, key):
        r = self._command('verify', path, {'key': key})
        return r.json()['success']

    # list files, folders, and locked folders in path
    def list_path(self, path=None, key=None):
        r = self.get(path, key)
        return r.json()

    def get(self, path, key):
        headers = self.get_headers(key)
        url = self.server_url + '/files/' + (path or '')
        return requests.get(url, headers=headers)

    def get_headers(self, key=None):
        headers = {}
        if self.api_key:
            headers['vault-api-key'] = self.api_key
        if key:
            headers['vault-key'] = key
        return headers

    def _command(self, command, path, data=None, files=None):
        headers = {}
        if self.api_key:
            headers['vault-api-key'] = self.api_key
        if data is None:
            data = {}
        data['command'] = command
        url = self.server_url + '/files/' + path
        return requests.post(url, headers=headers, data=data, files=files)

    def get_filesize(self, path):
        headers = {}
        if self.api_key:
            headers['vault-api-key'] = self.api_key
        url = self.server_url + '/files/' + (path or '')
        response = requests.head(url, headers=headers)
        filesize = int(response.headers['Content-Length']) / 1000
        return filesize
