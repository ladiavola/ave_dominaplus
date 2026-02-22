"""AVE maps and maps commands."""

import logging

_LOGGER = logging.getLogger(__name__)


class AveMapCommand:
    """Represents a command in the AVE map."""

    def __init__(self) -> None:
        """Initialize an AveMapCommand instance."""
        self.command_id: int = -1
        self.command_name: str = ""
        self.command_type: int = -1
        self.command_X: int = -1
        self.command_Y: int = -1
        self.icod: str = ""
        self.ico1: str = ""
        self.ico2: str = ""
        self.ico3: str = ""
        self.ico4: str = ""
        self.ico5: str = ""
        self.ico6: str = ""
        self.ico7: str = ""
        self.icoc: str = ""
        self.device_id: int = -1
        self.device_family: int = -1

    @staticmethod
    def _read_record_value(record: list[str], index: int) -> str:
        if index < len(record):
            return record[index]
        return ""

    @classmethod
    def from_ws_records(cls, record: list[str]) -> "AveMapCommand":
        """Create an AveMapCommand instance from a websocket record."""
        instance = cls()
        try:
            instance.command_id = int(cls._read_record_value(record, 0))
            instance.command_name = cls._read_record_value(record, 1)
            instance.command_type = int(cls._read_record_value(record, 2))
            instance.command_X = int(cls._read_record_value(record, 3))
            instance.command_Y = int(cls._read_record_value(record, 4))
            instance.icod = cls._read_record_value(record, 5)
            instance.ico1 = cls._read_record_value(record, 6)
            instance.ico2 = cls._read_record_value(record, 7)
            instance.ico3 = cls._read_record_value(record, 8)
            instance.ico4 = cls._read_record_value(record, 9)
            instance.ico5 = cls._read_record_value(record, 10)
            instance.ico6 = cls._read_record_value(record, 11)
            instance.ico7 = cls._read_record_value(record, 12)
            instance.icoc = cls._read_record_value(record, 13)
            instance.device_id = (
                int(cls._read_record_value(record, 14))
                if cls._read_record_value(record, 14).isdigit()
                else -1
            )
            instance.device_family = int(cls._read_record_value(record, 15))
        except (ValueError, IndexError):
            _LOGGER.exception("Error parsing command record")
        return instance


class AveArea:
    """Represents an area in the AVE map."""

    def __init__(self, area_id: int, name: str, order: int) -> None:
        """Initialize an AveArea instance."""
        self.id: int = area_id
        self.name: str = name
        self.order: int = order
        self.commands: list[AveMapCommand] = []
        self.commands_loaded: bool = False


class AveMap:
    """Represents the complete AVE map structure."""

    def __init__(self) -> None:
        """Initialize an AveMap instance."""
        self.areas_loaded: bool = False
        self.command_loaded: bool = False
        self.areas: dict[int, AveArea] = {}

    def load_areas_from_wsrecords(self, records: list[list]) -> None:
        """Load areas from websocket reply records."""
        for record in records:
            area_id = int(record[0])
            area_name = record[1]
            area_order = int(record[2])
            self.areas[area_id] = AveArea(area_id, area_name, area_order)
        self.areas_loaded = True

    def load_area_commands(self, area_id: int, records: list[list[str]]) -> None:
        """Load commands for a specific area from websocket reply records."""
        area = self.areas.get(area_id)
        if area:
            area.commands.extend(
                AveMapCommand.from_ws_records(record) for record in records
            )
            area.commands_loaded = True

            if all(a.commands_loaded for a in self.areas.values()):
                self.command_loaded = True

    def get_commands_by_family(self, family: int) -> list[AveMapCommand]:
        """Get all commands for a specific device family."""
        commands: list[AveMapCommand] = []
        for area in self.areas.values():
            commands.extend(
                command for command in area.commands if command.device_family == family
            )
        return commands

    def get_command_by_id_and_family(
        self, command_id: int, family: int
    ) -> AveMapCommand | None:
        """Get a specific command by its ID and device family."""
        for area in self.areas.values():
            for command in area.commands:
                if command.command_id == command_id and command.device_family == family:
                    return command
        return None

    def get_command_by_deviceid(self, device_id: int) -> AveMapCommand | None:
        """Get a specific command by its device ID."""
        for area in self.areas.values():
            for command in area.commands:
                if command.device_id == device_id:
                    return command
        return None

    def get_command_by_deviceid_and_family(
        self, device_id: int, family: int
    ) -> AveMapCommand | None:
        """Get a specific command by its device ID and family."""
        for area in self.areas.values():
            for command in area.commands:
                if command.device_id == device_id and command.device_family == family:
                    return command
        return None
