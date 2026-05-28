import os
import subprocess
from gi.repository import Nautilus, GObject

import socket


class FastShareExtension(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        pass

    def get_free_port(self):
        # Create a new socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            # Bind to port 0; the OS will assign an available port
            s.bind(('', 0))
            # Return the port number that was assigned
            return s.getsockname()[1]

    def launch_share(self, menu, files):
        for file in files:
            filepath = file.get_location().get_path()

            # Check if it is a directory or a file
            if os.path.isdir(filepath):
                flag = '--directory'
            else:
                flag = '--file'

            # Open zenity to ask temporary credentials for WebDAV
            zenity_username: str = subprocess.check_output(['zenity', '--entry', '--text=Enter username for WebDAV:']).decode('utf-8').strip()
            zenity_password: str = subprocess.check_output(['zenity', '--entry', '--text=Enter password for WebDAV:']).decode('utf-8').strip()

            free_port = self.get_free_port()

            # If empty, use anonymous
            if zenity_username == "":
                subprocess.Popen(['apprun', '{{USER_APPS}}/openwebdav.apprun', flag, filepath, '--capabilities', 'download', '--accounts', 'anonymous:anonymous', '--allow-anonymous', 'download', '--autoclose', '5min', '--port', str(free_port), '--ip', '*.*.*.*'])
            else:
                subprocess.Popen(['apprun', '{{USER_APPS}}/openwebdav.apprun', flag, filepath, '--capabilities', 'download', '--accounts', f'{zenity_username}:{zenity_password}', '--autoclose', '5min', '--port', str(free_port), '--ip', '*.*.*.*'])

            # Zenity show notification that file is shared in current local ip address
            current_local_ip = subprocess.check_output(['hostname', '-I']).decode('utf-8').strip()

            # Current local ip may contain multiple interfaces - select that begins with 192.168.xxx otherwise the first one
            found_ip = False
            for ip in current_local_ip.split():
                if ip.startswith('192.168.'):
                    current_local_ip = ip
                    found_ip = True
                    break
            
            if not found_ip:
                current_local_ip = current_local_ip.split()[0]

            subprocess.Popen(['zenity', '--info', '--text=File is shared in current local ip address: ' + current_local_ip + ':' + str(free_port)])

    def get_file_items(self, *args):
        files = args[-1]
        item = Nautilus.MenuItem(
            name='FastShare::Share',
            label='Share via WebDAV',
            tip='Share selected items',
            icon=''
        )
        item.connect('activate', self.launch_share, files)
        return [item]

    def get_background_items(self, *args):
        folder = args[-1]
        item = Nautilus.MenuItem(
            name='FastShare::ShareBackground',
            label='Share Current Directory via WebDAV',
            tip='Share current directory',
            icon=''
        )
        item.connect('activate', self.launch_share, [folder])
        return [item]
