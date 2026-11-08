"""Shared config constants; JSON Schema is the persisted input authority."""
SLOTS = tuple(f"{camp}-{i}" for camp in ("B", "R") for i in (1, 2, 3))
SECTORS = ("B-S1", "B-S2", "B-S3", "CM", "R-S1", "R-S2", "R-S3")
OBJECT_CLASSES = ("MILITARY_TRUCK", "MORTAR", "TANK", "MISSILE", "AMMO_BOX", "DRUM")
FACILITY_CODES = tuple(f"{camp}_{kind}" for camp in ("BLUE", "RED")
                       for kind in ("COMMS", "OUTPOST", "RADAR"))
BASE_CODES = tuple(f"{camp}_{kind}" for camp in ("BLUE", "RED")
                   for kind in ("COMMAND_POST", "MAINTENANCE", "SUPPLY_DEPOT"))
