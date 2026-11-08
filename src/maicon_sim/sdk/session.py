from dataclasses import dataclass,field


@dataclass
class SessionCache:
    """A participant restart preserves one session; a new match clears all evidence."""
    match_id:str | None=None
    observations:dict=field(default_factory=dict)
    reports:dict=field(default_factory=dict)

    def accept(self,handshake):
        changed=handshake["match_id"]!=self.match_id
        if changed:
            self.observations.clear()
            self.reports.clear()
            self.match_id=handshake["match_id"]
        return changed
