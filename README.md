# 🕸️ WebContentExtractor

A simple, no-cost, locally run web scraper built by someone who **doesn't know how to code** — just trying to solve real-world problems for fellow eCommerce founders.

---

## 🙋‍♂️ Who is this for?

- Bootstrapped eCommerce founders who didn’t come from a tech background  
- Small teams trying to extract content from their own or competitor sites  
- Curious folks looking to learn how to use AI + open-source tools without spending a dime

---

## 💡 What it does

This tool:
- Extracts all visible URLs and readable content from a given webpage  
- Lets you preview and optionally scrape blog sections too  
- Outputs results into `.txt` or `.json` files (not shared publicly)

---

## ⚙️ How to run it

1. **Clone the repo**
   ```bash
   git clone https://github.com/souravghosh1987/WebContentExtractor.git
   cd WebContentExtractor
   ```

2. **Create a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**
   ```bash
   python app.py
   ```

Then open your browser and visit: [http://localhost:5050](http://localhost:5050)

---

## 🛑 What it's *not*

- Not designed for large-scale or commercial scraping  
- Not built by a developer — don’t expect magic  
- Not using Selenium or headless browsers (yet)

---

## 🔐 Privacy Note

Scraped results (`scrape_results_*.txt`, `scraped_urls.json`) are **excluded from GitHub using `.gitignore`**, so nothing sensitive gets shared publicly.

---

## 🧠 Why I built this

I help 7-figure+ DTC brands grow, and I often needed quick ways to pull product, blog, or SEO content from public-facing pages. I don’t code — so I relied on AI to stitch together this basic Flask app.

If you're like me, I hope this gives you a head start.  
If you're more technical, feel free to fork and improve it!

---

## 🙏 Credits

- Python, Flask, BeautifulSoup, Trafilatura  
- ChatGPT (for helping me build the logic step by step)  
- Open-source devs who build tools that folks like me can lean on

---

## 🤝 Contributions welcome

PRs, cleanups, or even just ideas in Issues — all are welcome.
