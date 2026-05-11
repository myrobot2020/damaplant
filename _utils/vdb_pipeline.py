# _utils/vdb_pipeline.py
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from _utils.lancedb_helper import LanceDBHelper

_db = None

def get_db():
    global _db
    if _db is None:
        _db = LanceDBHelper()
    return _db

def get_sutta(sutta_id: str, stage: str) -> Optional[Dict]:
    """Get data from specific stage"""
    db = get_db()
    return db.get_by_stage(sutta_id, stage)

def get_all_suttas(stage: str, limit: int = 1000) -> List[Dict]:
    """Get all suttas from a stage"""
    db = get_db()
    table = db.db.open_table(db.table_name)
    results = table.search().where(f"stage = '{stage}'").limit(limit).to_list()
    return [json.loads(r['data']) for r in results]

def get_suttas_by_type(record_type: str, limit: int = 1000) -> List[Dict]:
    """Get all items by type (sutta, manga, chain, etc.)"""
    db = get_db()
    table = db.db.open_table(db.table_name)
    results = table.search().where(f"type = '{record_type}'").limit(limit).to_list()
    return [json.loads(r['data']) for r in results]

def save_to_vdb(record_id: str, stage: str, record_type: str, data: Dict, vector_field: str = None):
    """Save data to VDB"""
    db = get_db()
    return db.upsert(record_id, stage, record_type, data, vector_field)

def stage_exists(stage: str) -> bool:
    """Check if any data exists for a stage"""
    db = get_db()
    table = db.db.open_table(db.table_name)
    results = table.search().where(f"stage = '{stage}'").limit(1).to_list()
    return len(results) > 0

def get_stage_count(stage: str) -> int:
    """Get count of records in a stage"""
    db = get_db()
    table = db.db.open_table(db.table_name)
    results = table.search().where(f"stage = '{stage}'").limit(10000).to_list()
    return len(results)
