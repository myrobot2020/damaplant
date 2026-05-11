import json
import lancedb
import numpy as np
from pathlib import Path
from sentence_transformers import SentenceTransformer

class LanceDBHelper:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "vectordb" / "pipeline.lance"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.db_path))
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.table_name = "pipeline_data"
        self._init_table()
    
    def _init_table(self):
        if self.table_name not in self.db.table_names():
            sample = [{'id': 'init', 'stage': 'init', 'type': 'init', 'vector': [0.0]*384, 'data': '{}', 'timestamp': 0}]
            self.db.create_table(self.table_name, sample, mode="overwrite")
            self.db.open_table(self.table_name).delete("id = 'init'")
    
    def vectorize(self, text, max_length=2000):
        if not text:
            return [0.0]*384
        return self.model.encode(text[:max_length]).tolist()
    
    def upsert(self, record_id, stage, record_type, data, vector_field=None, vector_text=None):
        import time
        vector = None
        if vector_field and vector_field in data:
            vector = self.vectorize(str(data[vector_field]))
        elif vector_text:
            vector = self.vectorize(vector_text)
        
        record = {
            'id': record_id,
            'stage': stage,
            'type': record_type,
            'data': json.dumps(data, ensure_ascii=False),
            'timestamp': int(time.time() * 1000)
        }
        if vector:
            record['vector'] = vector
        
        table = self.db.open_table(self.table_name)
        existing = table.search().where(f"id = '{record_id}' and stage = '{stage}'").limit(1).to_list()
        if existing:
            table.delete(f"id = '{record_id}' and stage = '{stage}'")
        table.add([record])
        return True
    
    def get_latest(self, record_id):
        table = self.db.open_table(self.table_name)
        results = table.search().where(f"id = '{record_id}'").limit(1).to_list()
        return json.loads(results[0]['data']) if results else None
    
    def search_similar(self, query_text, record_type=None, limit=10):
        query_vec = self.vectorize(query_text)
        table = self.db.open_table(self.table_name)
        if record_type:
            results = table.search(query_vec).where(f"type = '{record_type}'").limit(limit).to_list()
        else:
            results = table.search(query_vec).limit(limit).to_list()
        return [{'id': r['id'], 'stage': r['stage'], 'type': r['type'], 
                 'data': json.loads(r['data']), 'score': float(1 - r['_distance'])} for r in results]
