from dataclasses import dataclass


@dataclass(frozen=True)
class Grant:
    id: str
    kind: str
    date: str
    child_uid: int
    approver: str
    created_at: str
    minutes: float | None = None
    budget: str | None = None
    until: str | None = None

    def to_dict(self):
        data = {
            'id': self.id,
            'kind': self.kind,
            'date': self.date,
            'child_uid': self.child_uid,
            'approver': self.approver,
            'created_at': self.created_at,
        }
        if self.minutes is not None:
            data['minutes'] = self.minutes
        if self.budget is not None:
            data['budget'] = self.budget
        if self.until is not None:
            data['until'] = self.until
        return data

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=str(data['id']),
            kind=str(data['kind']),
            date=str(data['date']),
            child_uid=int(data['child_uid']),
            approver=str(data['approver']),
            created_at=str(data['created_at']),
            minutes=data.get('minutes'),
            budget=data.get('budget'),
            until=data.get('until'),
        )


def extra_seconds(grants, budget, today):
    total = 0.0
    for grant in grants:
        if grant.kind == 'minutes' and grant.date == today and grant.budget == budget:
            total += float(grant.minutes or 0) * 60
    return total


def override_covers(grant, now):
    if grant.kind != 'until' or grant.date != str(now.date()) or not grant.until:
        return False
    from kids_policy.schedule import minutes_now, parse_hhmm
    return minutes_now(now) < parse_hhmm(grant.until)


def active_override(grants, now):
    for grant in grants:
        if override_covers(grant, now):
            return grant
    return None


def upsert_grant(grants, grant):
    for existing in grants:
        if existing.id == grant.id:
            return grants, existing, False
    return [*grants, grant], grant, True


def revoke_grant(grants, grant_id):
    kept = [grant for grant in grants if grant.id != grant_id]
    return kept, len(kept) != len(grants)
