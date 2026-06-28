import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'churn-iq-secret-2026'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///churn.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False