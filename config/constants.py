### Constants and Enums
import os
from datetime import datetime, date
from enum import Enum

PROJECT_NAME = "ShapeFlow Monitor"
PORT = 8050
FONT_AWESOME_CDN = "https://use.fontawesome.com/releases/v6.0.0/css/all.css"
DB_CONN_URL = "https://shapeflow-monitor-default-rtdb.europe-west1.firebasedatabase.app/"
ONSHAPE_GLOSSARY_URL = "https://cad.onshape.com/help/Content/Glossary/glossary.htm?tocpath=_____19"
START_DATE = date(2024, 4, 21).strftime('%d-%m-%Y')
END_DATE = datetime.now().strftime('%d-%m-%Y')


class RuntimeEnvironments(Enum):
    dev = "dev"
    prod = "prod"
    test = "test"


class DatabaseCollections(Enum):
    onshape_logs = "/onShapeLogs"
    uploaded_logs = "/uploaded-jsons"
    glossary_words = "/base-glossary-words"


ONSHAPE_LOGS_PATH = DatabaseCollections.onshape_logs.value
UPLOADED_LOGS_PATH = DatabaseCollections.uploaded_logs.value
GLOSSARY_WORDS_PATH = DatabaseCollections.glossary_words.value

runtime_environment = os.environ["RUNTIME_ENVIRONMENT"] = RuntimeEnvironments.dev.value
