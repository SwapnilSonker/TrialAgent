import asyncio
from playwright.async_api import async_playwright
import anthropic
import os
import json
import datetime
import re
from dotenv import load_dotenv

load_dotenv()

class WebAutomation:
    def __init__(self, task_description, api_key, session_dir="sessions"):
        self.task_description = task_description
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.client = anthropic.Client(api_key=api_key)
        self.session_dir = session_dir
        self.session_id = None
        self.step_history = []
        self.platform = None  # Will be set to 'notion', 'slack', or 'other'
        
        # Create sessions directory if it doesn't exist
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)
    
    async def connect_to_existing_browser(self, debugging_port=9222):
        """Connect to an existing Chrome browser with remote debugging enabled"""
        self.playwright = await async_playwright().start()
        
        try:
            # Connect to the existing browser instance
            self.browser = await self.playwright.chromium.connect_over_cdp(f"http://localhost:{debugging_port}")
            
            # Get the first context or create a new one
            if len(self.browser.contexts) > 0:
                self.context = self.browser.contexts[0]
            else:
                self.context = await self.browser.new_context()
            
            # Get the first page or create a new one
            if len(self.context.pages) > 0:
                self.page = self.context.pages[0]
            else:
                self.page = await self.context.new_page()
            
            # Detect the platform based on the current URL
            await self._detect_platform()
            
            # Create a session ID for this run
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_id = f"{self.platform}_session_{timestamp}"
            
            current_url = self.page.url
            print(f"Successfully connected to existing browser at URL: {current_url}")
            print(f"Detected platform: {self.platform}")
            
            if self.platform == "other":
                print("Warning: The current page doesn't appear to be Notion or Slack.")
                print("Consider navigating to one of these platforms first.")
            
            return True
        
        except Exception as e:
            print(f"Failed to connect to existing browser: {str(e)}")
            print("Make sure Chrome is running with remote debugging enabled:")
            print("chrome.exe --remote-debugging-port=9222")
            return False
    
    async def _detect_platform(self):
        """Detect which platform (Notion or Slack) is currently open"""
        current_url = self.page.url
        
        if "notion.so" in current_url:
            self.platform = "notion"
        elif "slack.com" in current_url:
            self.platform = "slack"
        else:
            self.platform = "other"
    
    async def get_page_state(self):
        """Extract current page information"""
        if not self.page:
            print("Error: No active page. Connect to a browser first.")
            return {}
        
        try:
            # Re-detect platform each time to handle navigation between platforms
            await self._detect_platform()
            
            current_state = {
                'url': self.page.url,
                'title': await self.page.title(),
                'html': await self.page.content(),
                'visible_text': await self.extract_visible_text(),
                'forms': await self.detect_forms(),
                'clickable_elements': await self.detect_clickable_elements(),
                'platform': self.platform
            }
            
            # Add platform-specific data
            if self.platform == "notion":
                current_state['platform_specific'] = await self.extract_notion_specific_elements()
            elif self.platform == "slack":
                current_state['platform_specific'] = await self.extract_slack_specific_elements()
            
            # Take a screenshot for reference
            screenshots_dir = os.path.join(self.session_dir, f"{self.session_id}_screenshots")
            if not os.path.exists(screenshots_dir):
                os.makedirs(screenshots_dir)
            
            screenshot_path = os.path.join(screenshots_dir, f"step_{len(self.step_history) + 1}.png")
            await self.page.screenshot(path=screenshot_path)
            
            return current_state
        
        except Exception as e:
            print(f"Error getting page state: {str(e)}")
            return {}
    
    async def extract_visible_text(self):
        """Extract visible text from the page"""
        text_elements = await self.page.evaluate("""
            () => {
                const textElements = [];
                const elements = document.querySelectorAll('h1, h2, h3, p, button, a, label, input[type="submit"], div[role="button"], [data-qa], [aria-label]');
                elements.forEach(el => {
                    const text = el.innerText || el.textContent;
                    if (text && text.trim()) {
                        textElements.push({
                            tag: el.tagName.toLowerCase(),
                            text: text.trim(),
                            dataQa: el.getAttribute('data-qa') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            id: el.id || ''
                        });
                    }
                });
                return textElements;
            }
        """)
        return text_elements
    
    async def detect_forms(self):
        """Detect forms on the page"""
        forms = await self.page.evaluate("""
            () => {
                const formData = [];
                const forms = document.querySelectorAll('form');
                forms.forEach((form, index) => {
                    const inputs = [];
                    form.querySelectorAll('input, select, textarea').forEach(input => {
                        inputs.push({
                            type: input.type || input.tagName.toLowerCase(),
                            name: input.name || '',
                            id: input.id || '',
                            placeholder: input.placeholder || '',
                            dataQa: input.getAttribute('data-qa') || '',
                            ariaLabel: input.getAttribute('aria-label') || ''
                        });
                    });
                    
                    formData.push({
                        index,
                        inputs,
                        submitButton: form.querySelector('button[type="submit"], input[type="submit"]') ? true : false
                    });
                });
                return formData;
            }
        """)
        return forms
    
    async def detect_clickable_elements(self):
        """Detect clickable elements"""
        clickables = await self.page.evaluate("""
            () => {
                const clickables = [];
                const elements = document.querySelectorAll('button, a, [role="button"], input[type="submit"], div[role="button"], [data-qa]:not(input), [aria-label]:not(input)');
                elements.forEach(el => {
                    const text = el.innerText || el.textContent || el.value;
                    const rect = el.getBoundingClientRect();
                    if (rect.width > 0 && rect.height > 0) {  // Element is visible
                        clickables.push({
                            tag: el.tagName.toLowerCase(),
                            text: text ? text.trim() : '',
                            href: el.href || '',
                            id: el.id || '',
                            classes: el.className || '',
                            dataQa: el.getAttribute('data-qa') || '',
                            ariaLabel: el.getAttribute('aria-label') || ''
                        });
                    }
                });
                return clickables;
            }
        """)
        return clickables
    
    async def extract_notion_specific_elements(self):
        """Extract Notion-specific elements and UI components"""
        notion_elements = await self.page.evaluate("""
            () => {
                const result = {
                    workspace_name: '',
                    page_title: '',
                    sidebar_visible: false,
                    top_level_pages: [],
                    action_buttons: []
                };
                
                // Try to get workspace name
                const workspaceElem = document.querySelector('.notion-sidebar-container .notion-workspace-name');
                if (workspaceElem) {
                    result.workspace_name = workspaceElem.innerText;
                }
                
                // Try to get page title
                const pageTitleElem = document.querySelector('.notion-page-content .notion-selectable .notion-page-block');
                if (pageTitleElem) {
                    result.page_title = pageTitleElem.innerText;
                }
                
                // Check if sidebar is visible
                result.sidebar_visible = !!document.querySelector('.notion-sidebar-container');
                
                // Get top level pages from sidebar
                const sidebarPages = document.querySelectorAll('.notion-sidebar-container a');
                sidebarPages.forEach(page => {
                    if (page.innerText) {
                        result.top_level_pages.push(page.innerText.trim());
                    }
                });
                
                // Find action buttons in the top bar
                const actionButtons = document.querySelectorAll('.notion-topbar button, .notion-topbar [role="button"]');
                actionButtons.forEach(button => {
                    const text = button.innerText || '';
                    if (text) {
                        result.action_buttons.push(text.trim());
                    }
                });
                
                return result;
            }
        """)
        return notion_elements
    
    async def extract_slack_specific_elements(self):
        """Extract Slack-specific elements and UI components"""
        slack_elements = await self.page.evaluate("""
            () => {
                const result = {
                    workspace_name: '',
                    current_channel: '',
                    sidebar_visible: false,
                    channels_list: [],
                    direct_messages_list: [],
                    current_user_info: {},
                    input_box_present: false
                };
                
                // Try to get workspace name
                const workspaceElem = document.querySelector('.p-workspace__sidebar_header_info_name');
                if (workspaceElem) {
                    result.workspace_name = workspaceElem.innerText;
                }
                
                // Try to get current channel
                const channelNameElem = document.querySelector('.p-view_header__channel_name');
                if (channelNameElem) {
                    result.current_channel = channelNameElem.innerText;
                }
                
                // Check if sidebar is visible
                result.sidebar_visible = !!document.querySelector('.p-channel_sidebar');
                
                // Get channels list
                const channelElems = document.querySelectorAll('[data-qa="channel_sidebar_name_channel"]');
                channelElems.forEach(channel => {
                    if (channel.innerText) {
                        result.channels_list.push(channel.innerText.trim());
                    }
                });
                
                // Get DMs list
                const dmElems = document.querySelectorAll('[data-qa="channel_sidebar_name_im"]');
                dmElems.forEach(dm => {
                    if (dm.innerText) {
                        result.direct_messages_list.push(dm.innerText.trim());
                    }
                });
                
                // Check if message input box is present
                result.input_box_present = !!document.querySelector('.p-message_input');
                
                // Try to get current user info
                const userStatusElem = document.querySelector('.p-ia__sidebar_header__user__button');
                if (userStatusElem) {
                    result.current_user_info.status = userStatusElem.getAttribute('aria-label') || '';
                    
                    // Try to get user name from the status button
                    const userNameElem = userStatusElem.querySelector('.p-ia__sidebar_header__user__name');
                    if (userNameElem) {
                        result.current_user_info.name = userNameElem.innerText;
                    }
                }
                
                return result;
            }
        """)
        return slack_elements
    
    async def get_ai_action(self, current_state):
        """Get next action from Anthropic API based on current state and task"""
        # Create a platform-specific part of the prompt
        platform_specific = ""
        if self.platform == "notion":
            platform_specific = """
            For Notion specifically:
            - Consider using selectors targeting div blocks, paragraphs, and page elements
            - Look for UI elements like "+ New page", sidebar toggles, and page titles
            - Note that Notion uses dynamic class names, so focus on text content and element hierarchy
            """
        elif self.platform == "slack":
            platform_specific = """
            For Slack specifically:
            - Prioritize using 'data-qa' attributes as selectors when available
            - For message input, target elements with class 'p-message_input'
            - For channel navigation, look for '[data-qa="channel_sidebar_name_channel"]' elements
            - Consider using aria-labels for interactive elements
            """
        else:
            platform_specific = """
            The current page doesn't appear to be Notion or Slack.
            Consider using general web automation techniques:
            - Target elements by ID, class, or text content
            - Use XPath for complex selections
            - Check for forms and input fields
            """
        
        # Create a prompt for the AI to generate the next action
        prompt = f"""
        # Web Automation Task for {self.platform.capitalize()}
        
        ## Task Description:
        {self.task_description}
        
        ## Current State:
        - Platform: {self.platform}
        - URL: {current_state['url']}
        - Page Title: {current_state['title']}
        
        ## Platform-Specific Elements:
        {json.dumps(current_state.get('platform_specific', {}), indent=2)}
        
        ## Visible Text Elements:
        {json.dumps(current_state['visible_text'][:20], indent=2)}
        
        ## Clickable Elements:
        {json.dumps(current_state['clickable_elements'][:20], indent=2)}
        
        ## Forms:
        {json.dumps(current_state['forms'], indent=2)}
        
        ## Platform Guidance:
        {platform_specific}
        
        ## Instructions:
        Based on the current page state and the task description, generate Python code using Playwright to perform the next logical action. The code should be a specific, self-contained snippet that will be executed.
        
        The code should:
        1. Take ONE specific action to progress the task (click, fill form, navigate, etc.)
        2. Be written for async Playwright
        3. Use the variable 'page' which is already defined
        4. Include proper waits for elements or navigation
        5. Be robust by using multiple selector strategies when possible
        
        Generate ONLY executable Python code without any explanations or markdown. The code will be directly executed.
        """
        
        # Call the Anthropic API
        response = self.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Extract the code from the response
        code = response.content[0].text.strip()
        
        # Remove any markdown code blocks if present
        if code.startswith("```python"):
            code = code.split("```python")[1]
        if code.endswith("```"):
            code = code.rsplit("```", 1)[0]
        
        code = code.strip()
        
        # Save the generated script to a file for reference
        script_dir = os.path.join(self.session_dir, f"{self.session_id}_scripts")
        if not os.path.exists(script_dir):
            os.makedirs(script_dir)
        
        script_path = os.path.join(script_dir, f"step_{len(self.step_history) + 1}.py")
        with open(script_path, 'w') as f:
            f.write(f"# Generated script for step {len(self.step_history) + 1}\n")
            f.write(f"# Platform: {self.platform}\n")
            f.write(f"# URL: {current_state['url']}\n")
            f.write(f"# Timestamp: {datetime.datetime.now().isoformat()}\n\n")
            f.write("async def run(page):\n")
            for line in code.split('\n'):
                f.write(f"    {line}\n")
        
        # Print the script for user visibility
        print(f"\n--- Generated Playwright Script for {self.platform.capitalize()} ---")
        print(code)
        print("--------------------------------")
        
        return code
    
    async def execute_action(self, code):
        """Execute the AI-generated code"""
        if not self.page:
            print("Error: No active page. Connect to a browser first.")
            return {'success': False, 'error': 'No active page'}
        
        try:
            # Prepare execution context
            page = self.page
            
            # Create temporary function with the code
            exec_globals = {'page': page, 'asyncio': asyncio}
            
            # Add debugging info
            print(f"\n--- Executing AI-generated code on {self.platform.capitalize()} ---")
            
            # Create and execute temporary function
            exec(f"async def _temp_action():\n{self._indent_code(code)}", exec_globals)
            await exec_globals['_temp_action']()
            
            # Wait for potential navigation or DOM changes
            await asyncio.sleep(2)
            
            # Add to step history
            self.step_history.append({
                'type': 'ai_action',
                'platform': self.platform,
                'code': code,
                'timestamp': datetime.datetime.now().isoformat(),
                'url': self.page.url
            })
            
            return {'success': True}
        except Exception as e:
            print(f"Action execution failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _indent_code(self, code):
        """Add proper indentation to the code"""
        lines = code.split('\n')
        indented_lines = ['    ' + line for line in lines]
        return '\n'.join(indented_lines)
    
    async def check_task_completion(self, current_state):
        """Ask the AI if the task is complete"""
        prompt = f"""
        # Task Completion Check for {self.platform.capitalize()}
        
        ## Task Description:
        {self.task_description}
        
        ## Current State:
        - Platform: {self.platform}
        - URL: {current_state['url']}
        - Page Title: {current_state['title']}
        
        ## Platform-Specific Elements:
        {json.dumps(current_state.get('platform_specific', {}), indent=2)}
        
        ## Visible Text Elements (sample):
        {json.dumps(current_state['visible_text'][:10], indent=2)}
        
        ## Question:
        Based on the task description and current page state, is the {self.platform.capitalize()} task completed?
        
        Return a JSON object with two fields:
        1. "is_complete": true or false
        2. "reason": brief explanation of your decision
        
        Only return the JSON object, nothing else.
        """
        
        response = self.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        try:
            result_text = response.content[0].text.strip()
            if result_text.startswith("```json"):
                result_text = result_text.split("```json")[1]
            if result_text.endswith("```"):
                result_text = result_text.rsplit("```", 1)[0]
            
            result = json.loads(result_text.strip())
            return result
        except:
            # If parsing fails, assume not complete
            return {
                'is_complete': False,
                'reason': "Unable to determine completion status"
            }
    
    async def manual_intervention(self, error_message):
        """Prompt for manual intervention and get user's choice on next steps"""
        print(f"\n=== USER INTERVENTION REQUIRED ({self.platform.capitalize()}) ===")
        print(f"Error: {error_message}")
        print("Please interact with the browser window to correct the issue.")
        print("\nOptions:")
        print("1: Continue automation after manual fix")
        print("2: Get a new AI suggestion for this step")
        print("3: Skip this step and continue")
        print("4: Navigate to a different URL and continue")
        print("5: Abort automation")
        
        choice = input("Enter your choice (1-5): ")
        
        if choice == '1':
            print("Continuing with next step...")
            return {"action": "continue"}
        elif choice == '2':
            print("Getting new AI suggestion...")
            return {"action": "new_suggestion"}
        elif choice == '3':
            print("Skipping this step...")
            return {"action": "skip"}
        elif choice == '4':
            new_url = input("Enter URL to navigate to: ")
            return {"action": "navigate", "url": new_url}
        else:
            print("Aborting automation...")
            return {"action": "abort"}
    
    async def run_workflow(self, max_steps=10):
        """Run the complete workflow with AI guidance"""
        if not self.page:
            print("Error: No active browser page. Connect to a browser first.")
            return False
        
        # Main control loop
        step_count = 0
        while step_count < max_steps:
            step_count += 1
            print(f"\n--- Step {step_count} ---")
            
            # Get current state and re-detect platform (in case of navigation)
            await self._detect_platform()
            current_state = await self.get_page_state()
            if not current_state:
                print("Failed to get page state. Aborting workflow.")
                return False
                
            print(f"Current platform: {self.platform}")
            print(f"Current page: {current_state['title']} ({current_state['url']})")
            
            # Check if task is complete
            completion_result = await self.check_task_completion(current_state)
            if completion_result['is_complete']:
                print(f"Task completed! Reason: {completion_result['reason']}")
                break
            
            # Get AI-generated action
            next_action_code = await self.get_ai_action(current_state)
            
            # Execute the action
            result = await self.execute_action(next_action_code)
            
            if not result['success']:
                print(f"Action failed: {result.get('error', 'Unknown error')}")
                
                # Take screenshot of error state
                error_dir = os.path.join(self.session_dir, f"{self.session_id}_errors")
                if not os.path.exists(error_dir):
                    os.makedirs(error_dir)
                await self.page.screenshot(path=os.path.join(error_dir, f"error_step_{step_count}.png"))
                
                # Simple recovery options
                print("Attempting basic recovery...")
                try:
                    # Wait a bit longer and try again
                    await asyncio.sleep(3)
                    result = await self.execute_action(next_action_code)
                    if result['success']:
                        print("Recovery successful after waiting.")
                        continue
                except Exception:
                    pass
                
                # Ask for user intervention and get action choice
                intervention = await self.manual_intervention(result.get('error', 'Unknown error'))
                
                if intervention["action"] == "continue":
                    # Update state after user intervention and continue
                    await self.get_page_state()
                    continue
                    
                elif intervention["action"] == "new_suggestion":
                    # Get a new AI suggestion and try again
                    print("Getting new AI action suggestion...")
                    next_action_code = await self.get_ai_action(current_state)
                    result = await self.execute_action(next_action_code)
                    if not result['success']:
                        print(f"New action also failed: {result.get('error', 'Unknown error')}")
                        # If the new suggestion also fails, get user intervention again
                        intervention = await self.manual_intervention(result.get('error', 'New action also failed'))
                        if intervention["action"] == "abort":
                            print("Aborting automation.")
                            break
                    continue
                    
                elif intervention["action"] == "skip":
                    # Skip this step and continue
                    print("Skipping this step and continuing...")
                    continue
                    
                elif intervention["action"] == "navigate":
                    # Navigate to a specified URL
                    try:
                        url = intervention.get("url", "")
                        if url:
                            print(f"Navigating to: {url}")
                            await self.page.goto(url)
                            await asyncio.sleep(2)
                            await self._detect_platform()  # Re-detect platform after navigation
                            print(f"New platform detected: {self.platform}")
                        continue
                    except Exception as e:
                        print(f"Navigation failed: {str(e)}")
                        continue
                    
                else:  # abort
                    print("Aborting automation.")
                    break
        
        if step_count >= max_steps:
            print("Maximum step limit reached. Task may not be complete.")
        
        # Export the script for future reference
        await self.export_full_script()
        return True
    
    async def export_full_script(self, output_path=None):
        """Export the full combined script of all steps"""
        if not output_path:
            output_path = os.path.join(self.session_dir, f"{self.session_id}_full_script.py")
        
        with open(output_path, 'w') as f:
            # Write imports and setup
            f.write("""import asyncio
from playwright.async_api import async_playwright

async def run_automation():
    async with async_playwright() as playwright:
        # Connect to existing browser with remote debugging
        browser = await playwright.chromium.connect_over_cdp("http://localhost:9222")
        context = browser.contexts[0]
        page = context.pages[0]
        
        print(f"Connected to existing browser at URL: {page.url}")
        
        try:
""")
            
            # Add each automation step
            for i, step in enumerate(self.step_history):
                if step['type'] == 'ai_action':
                    f.write(f"\n            # Step {i+1} - Platform: {step['platform']}\n")
                    
                    # Add the actual code with proper indentation
                    code_lines = step['code'].split('\n')
                    for line in code_lines:
                        f.write(f"            {line}\n")
                    
                    f.write(f"            await page.wait_for_timeout(1000)  # Short delay between actions\n")
            
            # Close everything properly
            f.write("""
            print("Automation completed successfully!")
        except Exception as e:
            print(f"Automation failed: {str(e)}")
            await page.screenshot(path="error.png")

# Run the automation
if __name__ == "__main__":
    asyncio.run(run_automation())
""")
        
        print(f"\nFull automation script exported to: {output_path}")
        return output_path
    
    async def close(self):
        """Close resources but don't close the browser"""
        # We don't close the browser since it was pre-existing
        if self.playwright:
            await self.playwright.stop()

async def main():
    # Replace with your Anthropic API key
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        api_key = input("Enter your Anthropic API key: ")
        os.environ["ANTHROPIC_API_KEY"] = api_key
    
    # Get task description from user input
    print("\n=== Web Automation for Notion and Slack ===")
    task_description = input("Enter your task description: ")
    
    # Create the automation instance
    automation = WebAutomation(task_description, api_key)
    
    # Connect to existing browser session
    connection_successful = await automation.connect_to_existing_browser(debugging_port=9222)
    if not connection_successful:
        print("Failed to connect to browser. Make sure Chrome is running with remote debugging enabled.")
        return
    
    # Set max steps
    max_steps = int(input("Enter maximum number of steps (default 10): ") or "10")
    
    # Run the automation workflow
    await automation.run_workflow(max_steps=max_steps)
    
    # Clean up
    await automation.close()

if __name__ == "__main__":
    asyncio.run(main())