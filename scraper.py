import requests
from bs4 import BeautifulSoup
import urllib.parse
import logging
import time
import random
import trafilatura
from urllib.robotparser import RobotFileParser

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# User-Agent strings to rotate between
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0'
]

def get_random_user_agent():
    """Return a random user agent from the list."""
    return random.choice(USER_AGENTS)

def is_allowed_by_robots(url):
    """Check if the URL is allowed by the site's robots.txt file."""
    try:
        parsed_url = urllib.parse.urlparse(url)
        robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
        
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        
        return rp.can_fetch("*", url)
    except Exception as e:
        logger.warning(f"Error checking robots.txt for {url}: {str(e)}")
        # If there's an error, we'll default to allowing the URL
        return True

def extract_internal_urls(base_url, max_urls=50, progress_callback=None, preview=False, blog_urls=None):
    """
    Extract internal URLs from a website's homepage or specific blog sections.
    
    Args:
        base_url: The URL of the homepage.
        max_urls: Maximum number of URLs to extract.
        progress_callback: Callback function to report progress.
        preview: If True, returns quickly with a sample of URLs.
        blog_urls: List of specific blog URLs to scrape (e.g., blog section pages).
        
    Returns:
        A list of internal URLs.
    """
    if progress_callback:
        progress_callback(0, f"Checking URL: {base_url}")
    
    # Parse the base URL to extract domain
    try:
        parsed_base = urllib.parse.urlparse(base_url)
        base_domain = parsed_base.netloc
    except Exception as e:
        logger.error(f"Error parsing URL {base_url}: {str(e)}")
        raise ValueError(f"Invalid URL: {str(e)}")
        
    # Check if the domain is valid
    if not base_domain:
        raise ValueError(f"Invalid URL: {base_url}")
    
    # Create a session for requests
    session = requests.Session()
    session.headers.update({'User-Agent': get_random_user_agent()})
    
    try:
        # Determine which URLs to process
        urls_to_process = [base_url]
        if blog_urls and isinstance(blog_urls, list):
            urls_to_process = blog_urls
            if progress_callback:
                progress_callback(5, f"Processing {len(blog_urls)} blog sections")
        
        # Process each URL and collect links
        all_links = []
        for i, url_to_process in enumerate(urls_to_process):
            if progress_callback:
                progress_callback(5 + i*3, f"Requesting: {url_to_process}")
            
            response = session.get(url_to_process, timeout=10)
            response.raise_for_status()
            
            # Check if the content type is HTML
            content_type = response.headers.get('Content-Type', '').lower()
            if 'text/html' not in content_type:
                logger.warning(f"URL does not return HTML content: {content_type}, skipping")
                continue
            
            # Parse the HTML
            if progress_callback:
                progress_callback(10 + i*3, f"Parsing HTML from: {url_to_process}")
            
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Extract all links from this page
            links = soup.find_all('a', href=True)
            all_links.extend(links)
        
        # Process links and filter for internal URLs
        internal_urls = set()
        
        if progress_callback:
            progress_callback(20, "Filtering for internal links")
            
        for i, link in enumerate(all_links):
            href = link['href'].strip()
            
            # Skip empty links, anchors, javascript
            if not href or href.startswith('#') or href.startswith('javascript:'):
                continue
                
            # Parse the link URL
            try:
                parsed = urllib.parse.urlparse(href)
                
                # Convert relative URLs to absolute
                if not parsed.netloc:
                    absolute_url = urllib.parse.urljoin(base_url, href)
                    parsed = urllib.parse.urlparse(absolute_url)
                else:
                    absolute_url = href
                    
                # Check if this is an internal URL (same domain)
                if parsed.netloc == base_domain:
                    # Normalize URL (remove fragments)
                    normalized_url = urllib.parse.urlunparse((
                        parsed.scheme,
                        parsed.netloc,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        ''  # Remove fragment
                    ))
                    
                    # Add to internal URLs if allowed by robots.txt
                    if is_allowed_by_robots(normalized_url):
                        internal_urls.add(normalized_url)
                    
                    # For preview mode, return quickly with a sample
                    if preview and len(internal_urls) >= max_urls:
                        return list(internal_urls)
            except Exception as e:
                logger.warning(f"Error processing link {href}: {str(e)}")
                continue
                
            # Update progress periodically
            if progress_callback and i % 10 == 0:
                progress = 20 + min(60, int((i / len(all_links)) * 60))
                progress_callback(progress, f"Processing links: {len(internal_urls)} internal URLs found")
        
        # Limit the number of URLs to the maximum
        internal_urls = list(internal_urls)[:max_urls]
        
        if progress_callback:
            progress_callback(80, f"Found {len(internal_urls)} internal URLs")
            
        return internal_urls
        
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP Error for {base_url}: {str(e)}")
        raise ValueError(f"HTTP Error: {str(e)}")
    except requests.exceptions.ConnectionError as e:
        logger.error(f"Connection Error for {base_url}: {str(e)}")
        raise ValueError(f"Connection Error: Could not connect to the server")
    except requests.exceptions.Timeout as e:
        logger.error(f"Timeout Error for {base_url}: {str(e)}")
        raise ValueError(f"Timeout Error: The request timed out")
    except requests.exceptions.RequestException as e:
        logger.error(f"Request Error for {base_url}: {str(e)}")
        raise ValueError(f"Request Error: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error processing {base_url}: {str(e)}")
        raise ValueError(f"Error processing URL: {str(e)}")

def extract_text_content(url):
    """
    Extract main text content from a webpage.
    
    Args:
        url: The URL of the webpage to scrape.
        
    Returns:
        The extracted text content.
    """
    try:
        # Use trafilatura for content extraction
        downloaded = trafilatura.fetch_url(url)
        
        if not downloaded:
            # Fall back to requests if trafilatura fetch fails
            headers = {'User-Agent': get_random_user_agent()}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            downloaded = response.text
        
        # Extract text with trafilatura (handles main content extraction well)
        text = trafilatura.extract(downloaded)
        
        # If trafilatura couldn't extract content, fall back to Beautiful Soup
        if not text:
            soup = BeautifulSoup(downloaded, 'lxml')
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()
                
            # Get text
            text = soup.get_text(separator='\n')
            
            # Clean up text
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
        
    except Exception as e:
        logger.error(f"Error extracting content from {url}: {str(e)}")
        return f"Error extracting content: {str(e)}"
