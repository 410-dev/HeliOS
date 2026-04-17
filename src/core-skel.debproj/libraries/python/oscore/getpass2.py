import sys

def getpass_star(prompt: str = "Password: ", stream=None):
    """
    * 로 표시되는 크로스 플랫폼 getpass 구현

    Args:
        prompt: 표시할 프롬프트 문자열
        stream: 프롬프트를 출력할 스트림 (기본값: /dev/tty 또는 sys.stderr)
    """

    # stream 처리: 원본 getpass 동작과 동일하게
    if stream is None:
        # 터미널이 연결된 경우 /dev/tty (Linux/macOS) 또는 sys.stderr 사용
        try:
            if sys.platform != "win32":
                stream = open("/dev/tty", "w")
            else:
                stream = sys.stderr
        except OSError:
            stream = sys.stderr

    # 프롬프트 출력 (stream 으로)
    stream.write(prompt)
    stream.flush()

    if sys.platform == "win32":
        # ── Windows ──────────────────────────────────────────
        import msvcrt

        password = []
        while True:
            ch = msvcrt.getwch()
            if ch in ('\r', '\n'):  # Enter
                stream.write('\n')
                stream.flush()
                break
            elif ch == '\x08':  # Backspace
                if password:
                    password.pop()
                    stream.write('\b \b')
                    stream.flush()
            elif ch == '\x03':  # Ctrl+C
                raise KeyboardInterrupt
            elif ch == '\x1b':  # ESC 무시
                continue
            else:
                password.append(ch)
                stream.write('*')
                stream.flush()
        return ''.join(password)

    else:
        # ── Linux / macOS ─────────────────────────────────────
        import tty
        import termios

        # 입력은 항상 /dev/tty (실제 터미널) 에서 받음
        try:
            tty_in = open("/dev/tty", "r")
            fd = tty_in.fileno()
        except OSError:
            tty_in = sys.stdin
            fd = sys.stdin.fileno()

        old_settings = termios.tcgetattr(fd)
        password = []
        try:
            tty.setraw(fd)
            while True:
                ch = tty_in.read(1)
                if ch in ('\r', '\n'):  # Enter
                    stream.write('\n')
                    stream.flush()
                    break
                elif ch == '\x7f':  # Backspace
                    if password:
                        password.pop()
                        stream.write('\b \b')
                        stream.flush()
                elif ch == '\x03':  # Ctrl+C
                    raise KeyboardInterrupt
                elif ch == '\x1b':  # ESC 무시
                    continue
                else:
                    password.append(ch)
                    stream.write('*')
                    stream.flush()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            # /dev/tty 를 직접 열었을 경우에만 닫음
            if tty_in is not sys.stdin:
                tty_in.close()

        return ''.join(password)


def getpass(prompt="Password: ", stream=None) -> str:
    import getpass as backend
    return backend.getpass(prompt, stream=stream)
