from typing import Any

JsonValue = Any  # the settings store is deliberately schema-free, like QSettings was
SettingsMap = dict[str, JsonValue]
ShortcutsMap = dict[str, str]
