import os
import subprocess
import locale
from urllib.parse import unquote
from gi.repository import Nautilus, GObject, Gio


class CreateNewFileExtension(GObject.GObject, Nautilus.MenuProvider):
    def __init__(self):
        super().__init__()
        self.setup_i18n()

    def setup_i18n(self):
        # 시스템 언어 감지
        lang = locale.getlocale()[0]
        if lang and lang.startswith('ko'):
            self.tr = {
                'menu_label': '새 파일 만들기...',
                'menu_desc': '현재 폴더에 빈 문서를 만듭니다.',
                'prompt_title': '새 파일 만들기',
                'prompt_text': '새 파일의 이름을 입력하세요:',
                'default_name': '새 파일.txt'
            }
        else:
            # 기본값 (영어)
            self.tr = {
                'menu_label': 'Create New File...',
                'menu_desc': 'Create a new empty document in this folder.',
                'prompt_title': 'Create New File',
                'prompt_text': 'Enter the name for the new file:',
                'default_name': 'New Document.txt'
            }

    def get_background_items(self, *args):
        # args의 마지막 요소가 항상 현재 폴더(Nautilus.FileInfo)입니다.
        current_folder = args[-1]

        item = Nautilus.MenuItem(
            name="NautilusPython::CreateNewFile",
            label=self.tr['menu_label'],
            tip=self.tr['menu_desc'],
            icon="document-new"
        )
        item.connect('activate', self.menu_activate_cb, current_folder)
        return [item]

    def menu_activate_cb(self, menu, current_folder):
        folder_uri = current_folder.get_uri()
        if not folder_uri.startswith("file://"):
            return

        # URI를 실제 파일 경로로 변환
        folder_path = unquote(folder_uri.replace("file://", ""))

        # Zenity를 사용하여 팝업창 띄우기
        try:
            result = subprocess.run([
                'zenity', '--entry',
                f'--title={self.tr["prompt_title"]}',
                f'--text={self.tr["prompt_text"]}',
                f'--entry-text={self.tr["default_name"]}'
            ], capture_output=True, text=True)

            # 사용자가 '확인'을 누른 경우 (returncode == 0)
            if result.returncode == 0:
                file_name = result.stdout.strip()

                # 아무 값도 입력하지 않고 확인을 누른 경우 기본값 사용
                if not file_name:
                    file_name = self.tr['default_name']

                new_file_path = os.path.join(folder_path, file_name)

                # 파일이 존재하지 않으면 빈 파일 생성
                if not os.path.exists(new_file_path):
                    with open(new_file_path, 'w') as f:
                        pass
        except Exception as e:
            print(f"Error creating file: {e}")
