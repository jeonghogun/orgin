from google.cloud.firestore_v1.base_client import BaseClient

def client() -> BaseClient: ...

class Query:
    ASCENDING: str
