import sys
from abc import ABC, abstractmethod
from collections import UserDict
from oscore.libatomic import atomic_write
from json import JSONDecodeError
import json
import os
import subprocess
import sys

class ConfigBase(ABC):
    """
    Config 와 ConfigView 가 공유하는 인터페이스.
    탐색 / 검증 / 읽기 / 쓰기의 공통 계약을 정의한다.

    sync() 는 의미가 다르므로 여기에 포함하지 않는다.
      - Config.sync()     : 파일에 저장 (소유자)
      - ConfigView.sync() : root_config.sync() 위임 (위임자)
    """

    # ------------------------------------------------------------------
    # 탐색
    # ------------------------------------------------------------------

    @abstractmethod
    def view(self, key, default=None) -> "ConfigView":
        """key 에 해당하는 값을 ConfigView 로 감싸 반환한다."""
        ...

    # ------------------------------------------------------------------
    # 검증
    # ------------------------------------------------------------------

    @abstractmethod
    def ensure(self, keys: list[str]) -> "ConfigBase":
        """지정한 키들이 모두 존재하는지 검증한다. 통과하면 self 반환."""
        ...

    @abstractmethod
    def is_type(self, key, *types: type) -> bool:
        """
        key 에 해당하는 값이 지정한 타입 중 하나인지 확인한다.

        cfg.is_type("Port", int)
        cfg.is_type("Value", int, float)
        """
        ...

    @abstractmethod
    def ensure_type(self, key, *types: type) -> "ConfigBase":
        """
        key 에 해당하는 값이 지정한 타입 중 하나인지 검증한다.
        통과하면 self 반환, 실패하면 TypeError.

        cfg.ensure_type("Port", int).view("Port")...
        """
        ...

    # ------------------------------------------------------------------
    # 읽기
    # ------------------------------------------------------------------

    @abstractmethod
    def get(self, key, default=None):
        """raw 값을 반환한다. 체이닝이 필요하면 .view(key) 를 사용할 것."""
        ...

    @abstractmethod
    def __getitem__(self, key): ...

    # ------------------------------------------------------------------
    # 쓰기
    # ------------------------------------------------------------------

    @abstractmethod
    def __setitem__(self, key, value): ...

    # ------------------------------------------------------------------
    # 공통 구현 (서브클래스에서 _value 또는 data 를 _data() 로 노출)
    # ------------------------------------------------------------------

    @abstractmethod
    def _data(self) -> dict:
        """내부 dict 를 반환한다. __contains__ / __iter__ / __len__ 에서 사용."""
        ...

    def __contains__(self, key):
        return key in self._data()

    def __iter__(self):
        return iter(self._data())

    def __len__(self):
        return len(self._data())


# ==============================================================================


class ConfigView(ConfigBase):
    """
    Config.view() 또는 ConfigView.view() 의 반환값.
    체이닝 전용 래퍼로, 원본 Config 와 부모 dict 에 대한 참조를 유지한다.
    """

    def __init__(
        self,
        value,
        key_path: str = "",
        root_config: "Config | None" = None,
        parent_data: "dict | None" = None,
        parent_key=None,
    ):
        self._value = value
        self._key_path = key_path
        self._root_config = root_config
        self._parent_data = parent_data
        self._parent_key = parent_key

    # ------------------------------------------------------------------
    # ConfigBase 계약 구현
    # ------------------------------------------------------------------

    def _data(self) -> dict:
        return self._value if isinstance(self._value, dict) else {}

    def _require_dict(self, method: str):
        if not isinstance(self._value, dict):
            raise TypeError(
                f"{method}() 는 dict 에만 사용할 수 있습니다. "
                f"'{self._key_path}' 의 실제 타입: {type(self._value).__name__}"
            )

    def view(self, key, default=None) -> "ConfigView":
        self._require_dict("view")
        child_path = f"{self._key_path}.{key}" if self._key_path else key
        return ConfigView(
            value=self._value.get(key, default),
            key_path=child_path,
            root_config=self._root_config,
            parent_data=self._value,
            parent_key=key,
        )

    def ensure(self, keys: list[str]) -> "ConfigView":
        self._require_dict("ensure")
        for key in keys:
            if key not in self._value:
                raise KeyError(f"필수 키 '{key}' 가 '{self._key_path}' 에 없습니다.")
        return self

    def is_type(self, key, *types: type) -> bool:
        self._require_dict("is_type")
        return isinstance(self._value.get(key), types)

    def ensure_type(self, key, *types: type) -> "ConfigView":
        self._require_dict("ensure_type")
        val = self._value.get(key)
        if not isinstance(val, types):
            type_names = " | ".join(t.__name__ for t in types)
            raise TypeError(
                f"'{self._key_path}.{key}' 의 타입이 올바르지 않습니다. "
                f"기대: {type_names}, 실제: {type(val).__name__}"
            )
        return self

    def get(self, key, default=None):
        self._require_dict("get")
        return self._value.get(key, default)

    def __getitem__(self, key):
        self._require_dict("__getitem__")
        return self._value[key]

    def __setitem__(self, key, value):
        self._require_dict("__setitem__")
        self._value[key] = value
        if self._parent_data is not None and self._parent_key is not None:
            self._parent_data[self._parent_key] = self._value

    # ------------------------------------------------------------------
    # ConfigView 전용
    # ------------------------------------------------------------------

    @property
    def value(self):
        return self._value

    def sync(self) -> bool:
        if self._root_config is None:
            raise RuntimeError(
                "이 ConfigView 는 Config 인스턴스와 연결되어 있지 않습니다. "
                "Config.view() 를 통해 생성한 ConfigView 에서만 sync() 를 호출할 수 있습니다."
            )
        return self._root_config.sync()

    def __repr__(self):
        return f"ConfigView(path={self._key_path!r}, value={self._value!r})"


# ==============================================================================


class Config(UserDict, ConfigBase):

    def __init__(
        self,
        path: str,
        path_is_abs: bool = False,
        enforce_global: bool = False,
        cascade_merge_mode: bool = False,
        cascade: bool = False,
        cascade_priorities: list[str] = None,
        cascade_priority_write_index: int = 0,
        logging: bool = False,
        resolve_pattern: bool = True,
    ):
        super().__init__()

        if logging:
            self._log = lambda message: print(f"[Config] {message}")
        else:
            self._log = lambda message: None

        if ".." in path:
            raise ValueError("Path cannot contain '..'")

        if not path.endswith(".json"):
            path += ".json"

        home_path: str = os.path.expanduser("~/.config/" + path)
        global_path: str = "/etc/" + path

        # Support all major OSes with appropriate paths
        if sys.platform == "linux":
            pass
        elif sys.platform == "win32":
            home_path = os.path.expanduser("~\\AppData\\Local\\" + path.replace("/", "\\"))
            global_path = os.path.join(os.environ.get("ProgramData", "C:\\ProgramData"), path.replace("/", "\\"))
        elif sys.platform == "darwin":
            home_path = os.path.expanduser("~/Library/Application Support/" + path)
            global_path = "/Library/Application Support/" + path

        # If supports AppContext, then use <box>/configs/<path>
        try:
            from AppContext import AppContext
            home_path = AppContext().file_in_box("configs/" + path)
        except ImportError:
            pass

        if cascade_merge_mode and not cascade:
            self._log("cascade_merge_mode is True but cascade is False. Enabling cascade mode.")
            cascade = True

        if enforce_global and cascade:
            raise ValueError("enforce_global cannot be True if cascade (or cascade_merge_mode) is True")

        self.path: str = None
        self.cascade_merge_priorities: list[str] | None = None
        self.cascade_merge_index: int = cascade_priority_write_index
        self.io_mode: int = 0
        self.data: dict = {}
        self.links: dict = {}
        self.resolve_pattern: bool = resolve_pattern

        if cascade:
            self._log("Validating cascade related settings...")
            if cascade_priorities is None or len(cascade_priorities) == 0:
                cascade_priorities = [home_path, global_path]
            if len(cascade_priorities) != len(set(cascade_priorities)):
                raise ValueError("cascade_priorities cannot contain duplicate paths")
            if len(cascade_priorities) <= cascade_priority_write_index:
                raise ValueError("cascade_priority_write_index must be less than the number of cascade_priorities")

            self._log(f"Cascade mode enabled. Prioritizing in order: {cascade_priorities}")

            if cascade_merge_mode:
                self._log("Cascade merge mode enabled.")
                self.cascade_merge_priorities = cascade_priorities
                self.io_mode = 1
            else:
                self._log("Cascade mode enabled without merge.")
                for priority in cascade_priorities:
                    if os.path.isfile(priority):
                        self._log(f"Config file found at {priority}.")
                        self.path = priority
                        break
                if self.path is None:
                    default = cascade_priorities[cascade_priority_write_index]
                    self._log(f"No config file found. Falling back to: {default}")
                    self.path = default
        else:
            self._log("Cascade mode disabled.")
            self.path = global_path if enforce_global else home_path
            self._log(f"Using {'global' if enforce_global else 'user local'} settings.")

        if path_is_abs:
            self.path = path

        self._log(f"Config path set to: {self.path}")

    def _log(self, message: str):
        pass

    # ------------------------------------------------------------------
    # ConfigBase 계약 구현
    # ------------------------------------------------------------------

    def _data(self) -> dict:
        return self.data

    def view(self, key, default=None) -> ConfigView:
        if self.resolve_pattern and key in self.links:
            try:
                raw = self._read_linked_file(key)
            except FileNotFoundError:
                raw = default
        else:
            raw = self.data.get(key, default)

        return ConfigView(
            value=raw,
            key_path=key,
            root_config=self,
            parent_data=self.data,
            parent_key=key,
        )

    def to_view(self) -> ConfigView:
        return ConfigView(
            value=self.data,
            key_path="",
            root_config=self,
            parent_data=None,
            parent_key=None,
        )

    def ensure(self, keys: list[str]) -> "Config":
        for key in keys:
            if key not in self.data and (not self.resolve_pattern or key not in self.links):
                raise KeyError(f"필수 키 '{key}' 가 config 에 없습니다.")
        return self

    def is_type(self, key, *types: type) -> bool:
        return isinstance(self.get(key), types)

    def ensure_type(self, key, *types: type) -> "Config":
        val = self.get(key)
        if not isinstance(val, types):
            type_names = " | ".join(t.__name__ for t in types)
            raise TypeError(
                f"'{key}' 의 타입이 올바르지 않습니다. "
                f"기대: {type_names}, 실제: {type(val).__name__}"
            )
        return self

    def get(self, key, default=None):
        if self.resolve_pattern and key in self.links:
            try:
                return self._read_linked_file(key)
            except FileNotFoundError:
                return default
        return self.data.get(key, default)

    def __getitem__(self, key):
        if self.resolve_pattern and key in self.links:
            try:
                return self._read_linked_file(key)
            except FileNotFoundError:
                raise KeyError(key)
        return self.data[key]

    def __setitem__(self, key, value):
        if self.resolve_pattern and key in self.links:
            link_path = self.links[key]
            if f"{key}:set" in self.links:
                try:
                    set_cmd: list[str] = self.links[f"{key}:set"].copy()
                    old_val = str(self.get(key, ""))
                    new_val = str(value)
                    for i, e in enumerate(set_cmd):
                        set_cmd[i] = e.replace("{new}", new_val).replace("{old}", old_val)
                    subprocess.run(set_cmd, shell=False, check=True)
                except subprocess.CalledProcessError as e:
                    raise ValueError(f"Command failed with exit code {e.returncode} for key: {key}") from e
                except FileNotFoundError as e:
                    raise ValueError(f"Command not found while executing set command for key: {key}") from e
            else:
                try:
                    os.makedirs(os.path.dirname(link_path), exist_ok=True)
                    if link_path.endswith(".json"):
                        atomic_write(link_path, json.dumps(value, indent=4, ensure_ascii=False))
                    else:
                        atomic_write(link_path, str(value))
                except IOError as e:
                    raise ValueError(f"IO error while saving linked config file: {link_path}") from e
                except TypeError as e:
                    raise ValueError(f"Invalid JSON format in configuration data for linked file: {link_path}") from e
        else:
            self.data[key] = value

    # ------------------------------------------------------------------
    # IO
    # ------------------------------------------------------------------

    def fetch(self) -> "Config":
        if self.io_mode == 0:
            self._fetch_general()
        elif self.io_mode == 1:
            self._fetch_cascade_merge()
        else:
            raise ValueError(f"Invalid value for io_mode: {self.io_mode}")

        if self.resolve_pattern:
            links = self.data.pop("_links", {})
            if isinstance(links, dict):
                self.links = links

        return self

    def sync(self) -> bool:
        if self.io_mode == 0:
            return self._sync_general()
        elif self.io_mode == 1:
            return self._sync_cascade_merge()
        else:
            raise ValueError(f"Invalid value for io_mode: {self.io_mode}")

    def to_str(self) -> str:
        dump_data = self.data.copy()
        if self.resolve_pattern and self.links:
            dump_data["_links"] = self.links
        return json.dumps(dump_data, indent=4, ensure_ascii=False)

    def exists(self) -> bool:
        if self.io_mode == 0:
            return os.path.isfile(self.path)
        elif self.io_mode == 1:
            return any(os.path.isfile(p) for p in self.cascade_merge_priorities)
        else:
            raise ValueError(f"Invalid value for io_mode: {self.io_mode}")

    # ------------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------------

    def _read_linked_file(self, key):
        link_path = self.links[key]
        try:
            with open(link_path, "r") as f:
                if link_path.endswith(".json"):
                    return json.load(f)
                else:
                    return f.read().strip()
        except FileNotFoundError:
            raise
        except JSONDecodeError:
            raise ValueError(f"Invalid JSON format in linked config file: {link_path}")
        except IOError as e:
            raise ValueError(f"IO error while loading linked config file: {link_path}") from e

    def _fetch_general(self) -> "Config":
        try:
            with open(self.path, "r") as f:
                self.data = json.load(f)
        except FileNotFoundError:
            self.data = {}
        except JSONDecodeError as e:
            raise ValueError(f"Invalid JSON format in config file: {self.path}") from e
        except IOError as e:
            raise ValueError(f"IO error while loading config file: {self.path}") from e
        return self

    def _fetch_cascade_merge(self) -> "Config":
        merged_data = {}
        for priority in self.cascade_merge_priorities[::-1]:
            if os.path.isfile(priority):
                try:
                    with open(priority, "r") as f:
                        merged_data.update(json.load(f))
                except JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON format in config file: {priority}") from e
                except IOError as e:
                    raise ValueError(f"IO error while loading config file: {priority}") from e
        self.data = merged_data
        return self

    def _sync_general(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            dump_data = self.data.copy()
            if self.resolve_pattern and self.links:
                dump_data["_links"] = self.links
            atomic_write(self.path, json.dumps(dump_data, indent=4, ensure_ascii=False))
            return True
        except IOError as e:
            raise IOError(f"IO error while saving config file: {self.path}") from e
        except TypeError as e:
            raise ValueError(f"Invalid JSON format in configuration data: {self.path}") from e

    def _sync_cascade_merge(self) -> bool:
        target_path: str = self.cascade_merge_priorities[self.cascade_merge_index]
        try:
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            dump_data = self.data.copy()
            if self.resolve_pattern and self.links:
                dump_data["_links"] = self.links
            atomic_write(target_path, json.dumps(dump_data, indent=4, ensure_ascii=False))
            return True
        except IOError as e:
            raise IOError(f"IO error while saving config file: {target_path}") from e
        except TypeError as e:
            raise ValueError(f"Invalid JSON format in configuration data: {target_path}") from e