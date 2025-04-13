import os
import logging
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
import scraper
import uuid
import time
import json
from threading import Thread
from werkzeug.utils import secure_filename
import urllib.parse
from datetime import datetime
from models import db, ScrapingJob, ScrapedUrl, ScrapedContent

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")

# Configure SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize the database
db.init_app(app)

# Create tables if they don't exist
with app.app_context():
    db.create_all()

# In-memory dictionary for active scraping jobs
scraping_jobs = {}

@app.route('/')
def index():
    # Get recent scraping jobs from database
    recent_jobs = ScrapingJob.query.filter_by(status='completed').order_by(ScrapingJob.end_time.desc()).limit(5).all()
    
    # Prepare job data for the template
    jobs_data = []
    for job in recent_jobs:
        urls_count = ScrapedUrl.query.filter_by(job_id=job.id).count()
        content_count = ScrapedContent.query.filter_by(job_id=job.id).count()
        duration = 0
        if job.start_time and job.end_time:
            duration = (job.end_time - job.start_time).total_seconds()
        
        jobs_data.append({
            'id': job.id,
            'url': job.url,
            'scrape_date': job.start_time,
            'duration': round(duration, 2),
            'urls_count': urls_count,
            'content_count': content_count
        })
    
    return render_template('index.html', recent_jobs=jobs_data)

@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    url = request.form.get('url', '').strip()
    max_pages = int(request.form.get('max_pages', 10))
    blog_urls_input = request.form.get('blog_urls', '').strip()
    
    # Validate URL
    if not url:
        return jsonify({'error': 'Please enter a URL'}), 400
    
    # Ensure URL has a scheme
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    try:
        # Less strict URL validation
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.netloc:
            return jsonify({'error': 'Invalid URL format: missing domain name'}), 400
    except Exception as e:
        return jsonify({'error': f'Invalid URL: {str(e)}'}), 400
    
    # Process optional blog URLs
    blog_urls = None
    if blog_urls_input:
        blog_urls = [url.strip() for url in blog_urls_input.split(',')]
        
        # Ensure all blog URLs have a scheme and validate them
        for i in range(len(blog_urls)):
            if not blog_urls[i].startswith(('http://', 'https://')):
                blog_urls[i] = 'https://' + blog_urls[i]
                
            try:
                parsed = urllib.parse.urlparse(blog_urls[i])
                if not parsed.netloc:
                    return jsonify({'error': f'Invalid blog URL: {blog_urls[i]}'}), 400
            except Exception as e:
                return jsonify({'error': f'Invalid blog URL: {blog_urls[i]}, {str(e)}'}), 400
    
    # Create a unique job ID
    job_id = str(uuid.uuid4())
    
    # Create job in database
    try:
        job = ScrapingJob(
            id=job_id,
            url=url,
            max_pages=max_pages,
            status='starting',
            progress=0,
            message='Initializing scraper...',
            start_time=datetime.utcnow()
        )
        db.session.add(job)
        db.session.commit()
    except Exception as e:
        logging.error(f"Error creating job in database: {str(e)}")
        return jsonify({'error': f'Database error: {str(e)}'}), 500
    
    # Initialize in-memory job status
    scraping_jobs[job_id] = {
        'status': 'starting',
        'progress': 0,
        'url': url,
        'max_pages': max_pages,
        'blog_urls': blog_urls,
        'start_time': time.time(),
        'message': 'Initializing scraper...',
        'urls_found': [],
        'content': {},
        'error': None
    }
    
    # Start scraping in a background thread
    thread = Thread(target=run_scraper, args=(job_id, url, max_pages, blog_urls))
    thread.daemon = True
    thread.start()
    
    return jsonify({'job_id': job_id})

def run_scraper(job_id, url, max_pages, blog_urls=None):
    try:
        # Update job status in memory and database
        if blog_urls:
            update_job_status(job_id, 'extracting_urls', f'Extracting URLs from {len(blog_urls)} blog sections...', 5)
        else:
            update_job_status(job_id, 'extracting_urls', 'Extracting internal URLs from homepage...', 5)
        
        # Extract internal URLs
        urls = scraper.extract_internal_urls(url, max_pages, 
                                           progress_callback=lambda p, m: update_progress(job_id, p, m),
                                           blog_urls=blog_urls)
        
        # Store URLs in memory
        scraping_jobs[job_id]['urls_found'] = urls
        scraping_jobs[job_id]['total_urls'] = len(urls)
        
        # Store URLs in database
        with app.app_context():
            # Get job from database
            job = ScrapingJob.query.get(job_id)
            if not job:
                logging.error(f"Job {job_id} not found in database")
                return
                
            # Add URLs to database
            for page_url in urls:
                scraped_url = ScrapedUrl(
                    job_id=job_id,
                    url=page_url,
                    processed=False
                )
                db.session.add(scraped_url)
            
            db.session.commit()
        
        if not urls:
            update_job_status(job_id, 'error', 'No internal URLs found on the homepage.', 0)
            with app.app_context():
                job = ScrapingJob.query.get(job_id)
                if job:
                    job.error = 'No internal URLs found'
                    db.session.commit()
            return
        
        # Scrape content from each URL
        update_job_status(job_id, 'scraping_content', f'Scraping content from {len(urls)} URLs...', 20)
        
        content_dict = {}
        for i, page_url in enumerate(urls):
            try:
                progress = 20 + ((i / len(urls)) * 80)  # Progress from 20% to 100%
                update_progress(job_id, progress, f'Scraping content from {page_url}')
                
                # Extract text content
                content = scraper.extract_text_content(page_url)
                if content:
                    content_dict[page_url] = content
                    
                    # Store content in database
                    with app.app_context():
                        # Find URL in database
                        url_record = ScrapedUrl.query.filter_by(job_id=job_id, url=page_url).first()
                        if url_record:
                            url_record.processed = True
                            
                            # Add content to database
                            scraped_content = ScrapedContent(
                                job_id=job_id,
                                url_id=url_record.id,
                                content=content
                            )
                            db.session.add(scraped_content)
                            db.session.commit()
                        
            except Exception as e:
                logging.error(f"Error scraping {page_url}: {str(e)}")
                continue
        
        # Save the results in memory
        scraping_jobs[job_id]['content'] = content_dict
        scraping_jobs[job_id]['status'] = 'completed'
        scraping_jobs[job_id]['message'] = 'Scraping completed'
        scraping_jobs[job_id]['progress'] = 100
        scraping_jobs[job_id]['end_time'] = time.time()
        scraping_jobs[job_id]['duration'] = scraping_jobs[job_id]['end_time'] - scraping_jobs[job_id]['start_time']
        
        # Update job status in database
        with app.app_context():
            job = ScrapingJob.query.get(job_id)
            if job:
                job.status = 'completed'
                job.progress = 100
                job.message = 'Scraping completed'
                job.end_time = datetime.utcnow()
        
        # Generate the output file
        output_path = f"scrape_results_{job_id}.txt"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"Web Scraping Results for {url}\n")
            f.write(f"Scraped on: {time.ctime()}\n")
            f.write(f"Total URLs processed: {len(urls)}\n")
            f.write(f"Total URLs with content: {len(content_dict)}\n\n")
            
            for page_url, text_content in content_dict.items():
                f.write(f"URL: {page_url}\n")
                f.write("=" * 80 + "\n")
                f.write(text_content.strip())
                f.write("\n\n" + "-" * 80 + "\n\n")
        
        # Save output file path in memory and database
        scraping_jobs[job_id]['output_file'] = output_path
        with app.app_context():
            job = ScrapingJob.query.get(job_id)
            if job:
                job.output_file = output_path
                db.session.commit()
        
    except Exception as e:
        logging.error(f"Error in scraping job {job_id}: {str(e)}")
        update_job_status(job_id, 'error', f'Error during scraping: {str(e)}', 0)
        
        # Update error in database
        with app.app_context():
            job = ScrapingJob.query.get(job_id)
            if job:
                job.error = str(e)
                db.session.commit()

def update_job_status(job_id, status, message, progress):
    """Update job status in memory and database"""
    # Update in memory
    if job_id in scraping_jobs:
        scraping_jobs[job_id]['status'] = status
        scraping_jobs[job_id]['message'] = message
        scraping_jobs[job_id]['progress'] = progress
    
    # Update in database
    with app.app_context():
        job = ScrapingJob.query.get(job_id)
        if job:
            job.status = status
            job.message = message
            job.progress = progress
            db.session.commit()

def update_progress(job_id, progress, message):
    if job_id in scraping_jobs:
        scraping_jobs[job_id]['progress'] = progress
        scraping_jobs[job_id]['message'] = message

@app.route('/job_status/<job_id>', methods=['GET'])
def job_status(job_id):
    # Try to get job from memory first
    if job_id in scraping_jobs:
        job = scraping_jobs[job_id]
        return jsonify({
            'status': job['status'],
            'progress': job['progress'],
            'message': job['message'],
            'urls_found': len(job.get('urls_found', [])),
            'content_count': len(job.get('content', {})),
            'error': job.get('error')
        })
    
    # If not in memory, try to get from database
    job_db = ScrapingJob.query.get(job_id)
    if not job_db:
        return jsonify({'error': 'Job not found'}), 404
    
    # Count URLs and content from database
    urls_count = ScrapedUrl.query.filter_by(job_id=job_id).count()
    content_count = ScrapedContent.query.filter_by(job_id=job_id).count()
    
    return jsonify({
        'status': job_db.status,
        'progress': job_db.progress,
        'message': job_db.message,
        'urls_found': urls_count,
        'content_count': content_count,
        'error': job_db.error
    })

@app.route('/results/<job_id>', methods=['GET'])
def results(job_id):
    # Try to get job from memory first
    if job_id in scraping_jobs:
        job = scraping_jobs[job_id]
        
        if job['status'] != 'completed':
            return redirect(url_for('index'))
        
        # Prepare data for the template from memory
        content_preview = {}
        for url, content in job['content'].items():
            # Limit preview to first 200 chars
            preview = content[:200] + "..." if len(content) > 200 else content
            content_preview[url] = preview
        
        return render_template('results.html', 
                              job_id=job_id,
                              url=job['url'],
                              duration=round(job.get('duration', 0), 2),
                              urls_count=len(job.get('urls_found', [])),
                              content_count=len(job.get('content', {})),
                              content_preview=content_preview)
    
    # If not in memory, try to get from database
    job_db = ScrapingJob.query.get(job_id)
    if not job_db or job_db.status != 'completed':
        return redirect(url_for('index'))
    
    # Get content from database
    content_previews = {}
    contents = ScrapedContent.query.filter_by(job_id=job_id).all()
    for content_record in contents:
        url_record = ScrapedUrl.query.get(content_record.url_id)
        if url_record:
            # Limit preview to first 200 chars
            preview = content_record.content[:200] + "..." if len(content_record.content) > 200 else content_record.content
            content_previews[url_record.url] = preview
    
    # Calculate duration
    duration = 0
    if job_db.start_time and job_db.end_time:
        duration = (job_db.end_time - job_db.start_time).total_seconds()
    
    # Count URLs
    urls_count = ScrapedUrl.query.filter_by(job_id=job_id).count()
    
    return render_template('results.html', 
                          job_id=job_id,
                          url=job_db.url,
                          duration=round(duration, 2),
                          urls_count=urls_count,
                          content_count=len(content_previews),
                          content_preview=content_previews)

@app.route('/download/<job_id>', methods=['GET'])
def download_results(job_id):
    output_file = None
    url = None
    
    # Try to get job from memory first
    if job_id in scraping_jobs and 'output_file' in scraping_jobs[job_id]:
        output_file = scraping_jobs[job_id]['output_file']
        url = scraping_jobs[job_id]['url']
    else:
        # If not in memory, try to get from database
        job_db = ScrapingJob.query.get(job_id)
        if job_db and job_db.output_file:
            output_file = job_db.output_file
            url = job_db.url
    
    if not output_file or not url or not os.path.exists(output_file):
        return redirect(url_for('index'))
    
    # Get the original URL's domain for the filename
    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc.replace('.', '_')
    
    return send_file(output_file, 
                     as_attachment=True, 
                     download_name=f"scrape_results_{domain}_{time.strftime('%Y%m%d')}.txt")

@app.route('/api/extract_preview', methods=['POST'])
def extract_preview():
    url = request.json.get('url', '')
    
    # Validate URL
    if not url:
        return jsonify({'error': 'Please enter a URL'}), 400
    
    # Ensure URL has a scheme
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # Less strict URL validation
        parsed_url = urllib.parse.urlparse(url)
        if not parsed_url.netloc:
            return jsonify({
                'success': False,
                'error': 'Invalid URL format: missing domain name'
            }), 400
        
        # Get a quick preview of URLs
        urls = scraper.extract_internal_urls(url, max_urls=5, preview=True)
        return jsonify({
            'success': True,
            'urls': urls[:5],  # Return only first 5 URLs
            'total': len(urls)
        })
    except Exception as e:
        logging.error(f"Error in URL preview for {url}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
