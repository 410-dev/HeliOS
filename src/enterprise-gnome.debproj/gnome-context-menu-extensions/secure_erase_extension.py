import os
import subprocess
from gi.repository import Nautilus, GObject

class SecureEraseExtension(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        pass

    def launch_secure_erase(self, menu, files):
        for file in files:
            filepath = file.get_location().get_path()
            
            try:
                fstype = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE', '-T', filepath], text=True).strip()
            except Exception:
                fstype = ""

            if fstype not in ['exfat', 'vfat']:
                if subprocess.call(['zenity', '--question', '--text', f'File location may have journaling or Copy-On-Write capability, which may result data recovery. Continue deletion for file: {os.path.basename(filepath)}?']) != 0:
                    continue


            # TODO: Retrieve user preferences for type and iterations
            subprocess.Popen(['python3', '{{OPT_LIBS}}/python/security/zerofill.py', '--type', 'random', '--iterations', '2', filepath])

    def get_file_items(self, *args):
        # Only show for regular files, not directories (optional)
        files = args[-1]
        
        item = Nautilus.MenuItem(
            name='SecureErase::Erase_File',
            label='Erase file securely',
            tip='Runs the secure erase script on this file',
            icon=''
        )
        item.connect('activate', self.launch_secure_erase, files)
        return [item]
    
