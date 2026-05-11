# _utils/vdb_reader.py
from _utils.lancedb_helper import LanceDBHelper

_db = None

def get_db():
    global _db
    if _db is None:
        _db = LanceDBHelper()
    return _db

def get_sutta(sutta_id: str, stage: str):
    """Get sutta data from VDB by stage"""
    db = get_db()
    return db.get_by_stage(sutta_id, stage)

def get_all_suttas(stage: str):
    """Get all suttas from a specific stage"""
    db = get_db()
    table = db.db.open_table(db.table_name)
    results = table.search().where(f"stage = '{stage}'").limit(1000).to_list()
    return [json.loads(r['data']) for r in results]

def get_commentary(sutta_id):
    """Get commentary from 03segment stage"""
    data = get_sutta(sutta_id, "03segment")
    return data.get('commentary', '') if data else ''

def get_chain(sutta_id):
    """Get chain from 07keys stage"""
    data = get_sutta(sutta_id, "07keys")
    return data.get('chain', {}) if data else {}

def get_commentary_classification(sutta_id):
    """Get classified commentary from 08commentary stage"""
    data = get_sutta(sutta_id, "08commentary")
    return data.get('classified_segments', {}) if data else {}
