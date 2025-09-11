from google.cloud import bigquery
from app.core.config import settings

def bq_client() -> bigquery.Client:
    return bigquery.Client(project=settings.GOOGLE_CLOUD_PROJECT)
