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

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Create Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")

# Dictionary to store scraping progress and results
scraping_jobs = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start_scraping', methods=['POST'])
def start_scraping():
    url = request.form.get('url', '').strip()
    max_pages = int(request.form.get('max_pages', 10))
    
    # Validate URL
    if not url:
        return jsonify({'error': 'Please enter a URL'}), 400
    
    # Ensure URL has a scheme
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    try:
        # Validate URL format
        parsed_url = urllib.parse.urlparse(url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            return jsonify({'error': 'Invalid URL format'}), 400
    except Exception as e:
        return jsonify({'error': f'Invalid URL: {str(e)}'}), 400
    
    # Create a unique job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    scraping_jobs[job_id] = {
        'status': 'starting',
        'progress': 0,
        'url': url,
        'max_pages': max_pages,
        'start_time': time.time(),
        'message': 'Initializing scraper...',
        'urls_found': [],
        'content': {},
        'error': None
    }
    
    # Start scraping in a background thread
    thread = Thread(target=run_scraper, args=(job_id, url, max_pages))
    thread.daemon = True
    thread.start()
    
    return jsonify({'job_id': job_id})

def run_scraper(job_id, url, max_pages):
    try:
        # Update job status
        scraping_jobs[job_id]['status'] = 'extracting_urls'
        scraping_jobs[job_id]['message'] = 'Extracting internal URLs from homepage...'
        
        # Extract internal URLs
        urls = scraper.extract_internal_urls(url, max_pages, 
                                           progress_callback=lambda p, m: update_progress(job_id, p, m))
        
        scraping_jobs[job_id]['urls_found'] = urls
        scraping_jobs[job_id]['total_urls'] = len(urls)
        
        if not urls:
            scraping_jobs[job_id]['status'] = 'error'
            scraping_jobs[job_id]['message'] = 'No internal URLs found on the homepage.'
            scraping_jobs[job_id]['error'] = 'No internal URLs found'
            return
        
        # Scrape content from each URL
        scraping_jobs[job_id]['status'] = 'scraping_content'
        scraping_jobs[job_id]['message'] = f'Scraping content from {len(urls)} URLs...'
        
        content_dict = {}
        for i, page_url in enumerate(urls):
            try:
                progress = (i / len(urls)) * 100
                update_progress(job_id, progress, f'Scraping content from {page_url}')
                
                # Extract text content
                content = scraper.extract_text_content(page_url)
                if content:
                    content_dict[page_url] = content
            except Exception as e:
                logging.error(f"Error scraping {page_url}: {str(e)}")
                continue
        
        # Save the results
        scraping_jobs[job_id]['content'] = content_dict
        scraping_jobs[job_id]['status'] = 'completed'
        scraping_jobs[job_id]['message'] = 'Scraping completed'
        scraping_jobs[job_id]['progress'] = 100
        scraping_jobs[job_id]['end_time'] = time.time()
        scraping_jobs[job_id]['duration'] = scraping_jobs[job_id]['end_time'] - scraping_jobs[job_id]['start_time']
        
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
        
        scraping_jobs[job_id]['output_file'] = output_path
        
    except Exception as e:
        logging.error(f"Error in scraping job {job_id}: {str(e)}")
        scraping_jobs[job_id]['status'] = 'error'
        scraping_jobs[job_id]['message'] = f'Error during scraping: {str(e)}'
        scraping_jobs[job_id]['error'] = str(e)
        scraping_jobs[job_id]['progress'] = 0

def update_progress(job_id, progress, message):
    if job_id in scraping_jobs:
        scraping_jobs[job_id]['progress'] = progress
        scraping_jobs[job_id]['message'] = message

@app.route('/job_status/<job_id>', methods=['GET'])
def job_status(job_id):
    if job_id not in scraping_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = scraping_jobs[job_id]
    return jsonify({
        'status': job['status'],
        'progress': job['progress'],
        'message': job['message'],
        'urls_found': len(job.get('urls_found', [])),
        'content_count': len(job.get('content', {})),
        'error': job.get('error')
    })

@app.route('/results/<job_id>', methods=['GET'])
def results(job_id):
    if job_id not in scraping_jobs:
        return redirect(url_for('index'))
    
    job = scraping_jobs[job_id]
    
    if job['status'] != 'completed':
        return redirect(url_for('index'))
    
    # Prepare data for the template
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

@app.route('/download/<job_id>', methods=['GET'])
def download_results(job_id):
    if job_id not in scraping_jobs or 'output_file' not in scraping_jobs[job_id]:
        return redirect(url_for('index'))
    
    output_file = scraping_jobs[job_id]['output_file']
    
    # Ensure the file exists
    if not os.path.exists(output_file):
        return redirect(url_for('index'))
    
    # Get the original URL's domain for the filename
    parsed_url = urllib.parse.urlparse(scraping_jobs[job_id]['url'])
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
        # Get a quick preview of URLs
        urls = scraper.extract_internal_urls(url, max_urls=5, preview=True)
        return jsonify({
            'success': True,
            'urls': urls[:5],  # Return only first 5 URLs
            'total': len(urls)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
