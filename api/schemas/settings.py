from typing import Annotated, Any

from pydantic import StringConstraints

# Bounds mirror the column widths in api/models/identity.py (String(120)), so an
# over-long identifier is a 422 here rather than a Postgres error surfacing as a 500.
# Values stay schema-free: any JSON is valid.
Key = Annotated[str, StringConstraints(min_length=1, max_length=120)]
Binding = Annotated[str, StringConstraints(min_length=1, max_length=120)]

JsonValue = Any  # the settings store is deliberately schema-free, like QSettings was
SettingsMap = dict[Key, JsonValue]
ShortcutsMap = dict[Key, Binding]
