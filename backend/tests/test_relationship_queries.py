import pytest
from app import db


@pytest.mark.parametrize('field', ['request_id', 'run_id'])
def test_indexed_relationship_isolation_and_order(tmp_path, monkeypatch, field):
    monkeypatch.setattr(db, 'DB_PATH', str(tmp_path / 'existing.db'))
    db.init()
    with db.connect() as c:
        # Simulate a database from the preceding release, with existing records.
        c.execute('DROP INDEX objects_request_id')
        c.execute('DROP INDEX objects_run_id')
        for id, tenant, kind, parent, created in [
            ('older', 'a', 'result', 'target', '2026-01-01'),
            ('newer', 'a', 'result', 'target', '2026-01-02'),
            ('other-tenant', 'b', 'result', 'target', '2026-01-03'),
            ('other-kind', 'a', 'offer', 'target', '2026-01-03'),
            ('other-parent', 'a', 'result', 'different', '2026-01-03'),
        ]:
            db.save(c, tenant, kind, {'id': id, field: parent, 'created_at': created})
    db.init()
    db.init()  # Upgrade remains idempotent.
    with db.connect() as c:
        assert [r['id'] for r in db.related(c, 'a', 'result', field, 'target')] == ['newer', 'older']
        assert db.related(c, 'a', 'result', field, 'missing') == []
        plan = ' '.join(str(tuple(row)) for row in c.execute(
            f"EXPLAIN QUERY PLAN SELECT body FROM objects WHERE tenant=? AND kind=? AND json_extract(body,'$.{field}')=? ORDER BY created DESC",
            ('a', 'result', 'target'),
        ))
        assert f'USING INDEX objects_{field}' in plan
        assert 'TEMP B-TREE' not in plan
        assert c.execute('SELECT COUNT(*) FROM objects').fetchone()[0] == 5
        with pytest.raises(ValueError):
            db.related(c, 'a', 'result', 'unknown', 'target')
