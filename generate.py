import os
import re
import anthropic
import asyncio
from playwright.async_api import async_playwright
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize the Anthropic client
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Directory for saving sessions and scripts
SESSION_PATH = os.path.join(os.getcwd(), "playwright_session")
SCRIPTS_PATH = os.path.join(os.getcwd(), "scripts")
os.makedirs(SESSION_PATH, exist_ok=True)
os.makedirs(SCRIPTS_PATH, exist_ok=True)

async def extract_page_elements(url):
    """Extract important elements from the page to inform script generation"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            await page.goto(url)
            
            # Extract key page information
            title = await page.title()
            
            # Extract important interactive elements (buttons, inputs, links, etc.)
            elements = await page.query_selector_all('button, input, a[href], .nav-item, .menu-item, [role="button"], [role="menuitem"]')
            element_data = []
            
            for element in elements:
                # Get element properties
                tag = await element.evaluate('el => el.tagName.toLowerCase()')
                text = await element.evaluate('el => el.textContent?.trim() || ""')
                
                # Get attributes
                id_attr = await element.get_attribute('id') or ""
                class_attr = await element.get_attribute('class') or ""
                href = await element.get_attribute('href') or ""
                data_attrs = await element.evaluate('''el => {
                    return Object.keys(el.dataset)
                      .map(key => `data-${key}="${el.dataset[key]}"`)
                      .join(' ');
                }''')
                
                # Compile info about this element
                element_info = f"{tag}"
                if id_attr:
                    element_info += f" id='{id_attr}'"
                if class_attr:
                    element_info += f" class='{class_attr}'"
                if href:
                    element_info += f" href='{href}'"
                if data_attrs:
                    element_info += f" {data_attrs}"
                if text:
                    element_info += f" text='{text}'"
                
                element_data.append(element_info)
            
            # Get overall page structure
            structure = await page.evaluate('''() => {
                function getStructure(element, depth = 0) {
                    if (!element) return '';
                    
                    const indent = ' '.repeat(depth * 2);
                    const tag = element.tagName.toLowerCase();
                    const id = element.id ? `#${element.id}` : '';
                    const classes = element.className && typeof element.className === 'string' ? 
                        `.${element.className.trim().replace(/\s+/g, '.')}` : '';
                    
                    let result = `${indent}${tag}${id}${classes}\\n`;
                    
                    for (const child of Array.from(element.children).slice(0, 5)) {
                        if (depth < 3) { // Limit depth to prevent excessive output
                            result += getStructure(child, depth + 1);
                        }
                    }
                    
                    return result;
                }
                
                return getStructure(document.body);
            }''')
            
            await browser.close()
            
            return {
                "url": url,
                "title": title,
                "elements": element_data,
                "structure": structure
            }
        except Exception as e:
            await browser.close()
            return {
                "url": url,
                "error": str(e),
                "elements": [],
                "structure": "Could not extract page structure"
            }

async def parse_task_for_url(task):
    """Extract the website URL from the task description"""
    # List of common websites and their URLs
    sites = {
        "notion": "https://www.notion.so",
        "google": "https://www.google.com",
        "gmail": "https://mail.google.com",
        "youtube": "https://www.youtube.com",
        "github": "https://github.com",
        "twitter": "https://twitter.com",
        "x": "https://x.com",
        "facebook": "https://www.facebook.com",
        "linkedin": "https://www.linkedin.com",
        "amazon": "https://www.amazon.com",
        "reddit": "https://www.reddit.com"
    }
    
    # Look for site names in the task
    task_lower = task.lower()
    for site, url in sites.items():
        if site in task_lower:
            return url
    
    # Look for explicit URLs in the task
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, task)
    if urls:
        return urls[0]
    
    # Default URL if none found
    return None

async def generate_playwright_script(task, page_data):
    """Generate a Playwright script based on the task and page data"""
    
    # Define boilerplate code that must be included
    boilerplate = """
import os
from playwright.sync_api import sync_playwright

# Create a session directory if it doesn't exist
SESSION_PATH = os.path.join(os.getcwd(), "playwright_session")
os.makedirs(SESSION_PATH, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch_persistent_context(SESSION_PATH, headless=False)
    page = browser.new_page()
    """
    
    # Format page elements as a string
    elements_str = "\n".join(page_data["elements"][:50])  # Limit to prevent token overuse
    
    # Construct the prompt
    prompt = f"""
    Create a Playwright script to "{task}". The target website is {page_data['url']} with the title "{page_data['title']}".
    
    Use the extracted page elements to create precise selectors:
    ```
    {elements_str}
    ```
    
    Page structure overview:
    ```
    {page_data['structure'][:500]}  
    ```
    
    Your script MUST:
    1. Be in Python using Playwright's sync API
    2. Include and build upon this exact boilerplate code:
    ```python
    {boilerplate}
    ```
    3. Use precise selectors based on the provided page elements
    4. Include proper error handling and waiting for elements
    5. Be robust against small UI changes
    6. Include comments explaining key steps
    7. Don't use unnecessary selectors
    8. Don't include the code in ```code``` in this response
    
    Generate ONLY the Python code without explanations. The script should be complete and ready to run.
    """
    
    response = client.messages.create(
        model="claude-3-7-sonnet-20250219",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )
    
    script_content = response.content[0].text
    
    # Extract code blocks if the response includes markdown formatting
    if "```python" in script_content and "```" in script_content:
        # Extract code between python code blocks
        start = script_content.find("```python") + 9
        end = script_content.rfind("```")
        if start > 9 and end > start:
            script_content = script_content[start:end].strip()
    
    # Create a unique script name based on the task
    script_name = re.sub(r'[^a-zA-Z0-9]', '_', task.lower())[:30]
    script_path = os.path.join(SCRIPTS_PATH, f"{script_name}.py")
    
    with open(script_path, "w") as file:
        file.write(script_content)

    return {
        "message": f"Script for '{task}' generated successfully!",
        "script_path": script_path,
        "script_content": script_content
    }

async def main():
    # Get task from user
    task = input("Enter your automation task (e.g., 'open notion move to categories and take a snapshot'): ")
    
    # Parse the URL from the task
    url = await parse_task_for_url(task)
    
    if not url:
        url = input("Could not determine the website. Please enter the URL: ")
    
    print(f"\nExtracting page elements from {url}...")
    page_data = await extract_page_elements(url)
    
    if "error" in page_data and page_data["error"]:
        print(f"Error extracting page data: {page_data['error']}")
        return
    
    print(f"Successfully extracted {len(page_data['elements'])} elements from {page_data['title']}")
    print("Generating Playwright script...")
    
    result = await generate_playwright_script(task, page_data)
    
    print(result["message"])
    print(f"Script saved to: {result['script_path']}")
    
    run_script = input("\nDo you want to run this script now? (y/n): ")
    if run_script.lower() == 'y':
        print(f"\nRunning script: {result['script_path']}")
        os.system(f"python {result['script_path']}")

if __name__ == "__main__":
    asyncio.run(main())