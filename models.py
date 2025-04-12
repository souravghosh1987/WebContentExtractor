from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class ScrapingJob(db.Model):
    __tablename__ = 'scraping_jobs'
    
    id = db.Column(db.String(36), primary_key=True)  # UUID as string
    url = db.Column(db.String(255), nullable=False)
    max_pages = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'starting', 'extracting_urls', 'scraping_content', 'completed', 'error'
    progress = db.Column(db.Float, nullable=False, default=0)
    message = db.Column(db.String(255))
    error = db.Column(db.Text)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    output_file = db.Column(db.String(255))
    
    # Relationships
    urls = relationship("ScrapedUrl", back_populates="job", cascade="all, delete-orphan")
    contents = relationship("ScrapedContent", back_populates="job", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ScrapingJob {self.id}>"
    
class ScrapedUrl(db.Model):
    __tablename__ = 'scraped_urls'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), db.ForeignKey('scraping_jobs.id'), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    processed = db.Column(db.Boolean, default=False)
    
    # Relationships
    job = relationship("ScrapingJob", back_populates="urls")
    content = relationship("ScrapedContent", back_populates="url", uselist=False, cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<ScrapedUrl {self.url}>"
    
class ScrapedContent(db.Model):
    __tablename__ = 'scraped_contents'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(36), db.ForeignKey('scraping_jobs.id'), nullable=False)
    url_id = db.Column(db.Integer, db.ForeignKey('scraped_urls.id'), nullable=False)
    content = db.Column(db.Text)
    scraped_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    job = relationship("ScrapingJob", back_populates="contents")
    url = relationship("ScrapedUrl", back_populates="content")
    
    def __repr__(self):
        return f"<ScrapedContent for URL ID {self.url_id}>"