import pandas as pd
import joblib
import psycopg2
from psycopg2.extras import execute_values
import re
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import nltk
import os
import django
from django.conf import settings
import sys
import logging
from transformers import BertTokenizer, BertForSequenceClassification
import torch

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set up Python path
BASE_DIR = r'C:\Users\LENOVO\job_recommendation_system\job_rec'
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)
    logger.info(f"Added {BASE_DIR} to sys.path")

# Verify sys.path for debugging
logger.info(f"sys.path: {sys.path}")

# Set up Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_rec.settings')
try:
    django.setup()
except Exception as e:
    logger.error(f"Failed to set up Django: {e}")
    raise

# Download NLTK data
nltk.download('punkt', quiet=True)
nltk.download('stopwords', quiet=True)

# Text preprocessing function
def preprocess_text(text):
    logger.info("Preprocessing text")
    text = text.lower()
    text = re.sub(r'[^a-zA-Z\s]', '', text)
    tokens = word_tokenize(text)
    stop_words = set(stopwords.words('english'))
    tokens = [word for word in tokens if word not in stop_words]
    return ' '.join(tokens)

# Function to truncate long fields
def truncate_field(field, max_length, field_name):
    if field and isinstance(field, str) and len(field) > max_length:
        logger.warning(f"Truncating {field_name} from {len(field)} to {max_length} characters")
        return field[:max_length]
    return field

# Database connection
logger.info("Connecting to database")
db_settings = settings.DATABASES['default']
try:
    conn = psycopg2.connect(
        dbname=db_settings['NAME'],
        user=db_settings['USER'],
        password=db_settings['PASSWORD'],
        host=db_settings['HOST'],
        port=db_settings['PORT']
    )
    cursor = conn.cursor()
except Exception as e:
    logger.error(f"Database connection failed: {e}")
    raise

# Fetch data from the jobs table
logger.info("Fetching data from jobs table")
cursor.execute("SELECT id, title, company, location, job_type, date_posted, url, created_at, source, description FROM jobs")
rows = cursor.fetchall()
if not rows:
    logger.warning("No data found in jobs table")
    cursor.close()
    conn.close()
    raise ValueError("No data found in jobs table")

# Prepare data for prediction
job_data = []
for row in rows:
    job_id, title, company, location, job_type, date_posted, url, created_at, source, description = row
    url = truncate_field(url, 255, "url")
    description = truncate_field(description, 1000, "description")
    job_data.append((job_id, title, company, location, job_type, date_posted, url, source, description))

# Predict categories (industries)
ids = [item[0] for item in job_data]
titles = [item[1] for item in job_data]
companies = [item[2] for item in job_data]
locations = [item[3] for item in job_data]
job_types = [item[4] for item in job_data]
date_posteds = [item[5] for item in job_data]
urls = [item[6] for item in job_data]
sources = [item[7] for item in job_data]
descriptions = [item[8] for item in job_data]

# Load the LabelEncoder
label_encoder_path = r'C:\Users\LENOVO\job_recommendation_system\job_rec\job_recommendation\model\label_encoder.pkl'
logger.info(f"Loading LabelEncoder from {label_encoder_path}")
if not os.path.exists(label_encoder_path):
    logger.error(f"LabelEncoder file not found at {label_encoder_path}")
    raise FileNotFoundError(f"LabelEncoder file not found at {label_encoder_path}")
label_encoder = joblib.load(label_encoder_path)

# Load BERT model and tokenizer
model_path = r'C:\Users\LENOVO\job_recommendation_system\job_rec\job_recommendation\model'
logger.info(f"Loading BERT model from {model_path}")
try:
    model = BertForSequenceClassification.from_pretrained(model_path)
    tokenizer = BertTokenizer.from_pretrained(model_path)
    
    # Preprocess and tokenize titles
    logger.info("Preprocessing and tokenizing titles for BERT")
    titles_preprocessed = [preprocess_text(title) for title in titles]
    inputs = tokenizer(titles_preprocessed, return_tensors='pt', padding=True, truncation=True, max_length=512)
    
    # Predict
    logger.info("Running BERT predictions")
    with torch.no_grad():
        outputs = model(**inputs)
        predictions = torch.argmax(outputs.logits, dim=1).numpy()
    
    # Decode predictions
    industries = label_encoder.inverse_transform(predictions)
except Exception as e:
    logger.error(f"Error loading or using BERT model: {e}")
    raise

# Insert cleaned data into jobs_cleaned table
logger.info("Inserting cleaned data into jobs_cleaned table")
insert_query = """
    INSERT INTO jobs_cleaned (id, title, company, location, job_type, date_posted, url, source, description, category)
    VALUES %s
    ON CONFLICT (id) DO UPDATE
    SET title = EXCLUDED.title,
        company = EXCLUDED.company,
        location = EXCLUDED.location,
        job_type = EXCLUDED.job_type,
        date_posted = EXCLUDED.date_posted,
        url = EXCLUDED.url,
        source = EXCLUDED.source,
        description = EXCLUDED.description,
        category = EXCLUDED.category
"""
insert_data = [(
    job_id, title, company, location, job_type, date_posted, url, source, description, category
) for job_id, title, company, location, job_type, date_posted, url, source, description, category in zip(
    ids, titles, companies, locations, job_types, date_posteds, urls, sources, descriptions, industries
)]
execute_values(cursor, insert_query, insert_data, page_size=1000)

# Commit changes and close connection
logger.info("Committing changes and closing database connection")
conn.commit()
cursor.close()
conn.close()

print("Categorization and insertion completed.")