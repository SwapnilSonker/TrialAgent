import asyncio
import json
import os
import pickle
import datetime
from playwright.async_api import async_playwright
import anthropic

class AIControlledAutomation:
    def __init__(self, task_description, api_key, session_dir="sessions"):
        self.task_description = task_description
        self.browser = None
        self.context = None
        self.page = None
        self.current_state = {}
        self.client = anthropic.Client(api_key=api_key)
        self.session_dir = session_dir
        self.session_id = None
        self.step_history = []
        
        # Create sessions directory if it doesn't exist
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)
    
    async def initialize(self, session_id=None):
        """Initialize the browser session, optionally from a saved session"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=False)
        
        if session_id and self._session_exists(session_id):
            # Load existing session
            self.session_id = session_id
            session_data = self._load_session(session_id)
            
            # Restore browser context with storage state
            self.context = await self.browser.new_context(
                storage_state=os.path.join(self.session_dir, f"{session_id}_storage.json")
            )
            
            # Restore page
            self.page = await self.context.new_page()
            await self.page.goto(session_data['last_url'])
            
            # Restore step history
            self.step_history = session_data.get('step_history', [])
            
            print(f"Resumed session {session_id} at URL: {session_data['last_url']}")
            print(f"Completed {len(self.step_history)} steps previously")
        else:
            # Create new session
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            self.session_id = f"session_{timestamp}"
            self.context = await self.browser.new_context()
            self.page = await self.context.new_page()
            print(f"Created new session: {self.session_id}")
    
    async def get_page_state(self):
        """Extract current page information"""
        current_state = {
            'url': self.page.url,
            'title': await self.page.title(),
            'html': await self.page.content(),
            'visible_text': await self.extract_visible_text(),
            'forms': await self.detect_forms(),
            'clickable_elements': await self.detect_clickable_elements()
        }
        
        # Take a screenshot for visual context
        screenshots_dir = os.path.join(self.session_dir, f"{self.session_id}_screenshots")
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)
        
        screenshot_path = os.path.join(screenshots_dir, f"step_{len(self.step_history) + 1}.png")
        await self.page.screenshot(path=screenshot_path)
        
        self.current_state = current_state
        return current_state
    
    async def extract_visible_text(self):
        """Extract visible text from the page"""
        text_elements = await self.page.evaluate("""
            () => {
                const textElements = [];
                const elements = document.querySelectorAll('h1, h2, h3, p, button, a, label, input[type="submit"]');
                elements.forEach(el => {
                    const text = el.innerText || el.textContent;
                    if (text && text.trim()) {
                        textElements.push({
                            tag: el.tagName.toLowerCase(),
                            text: text.trim()
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
                            placeholder: input.placeholder || ''
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
                const elements = document.querySelectorAll('button, a, [role="button"], input[type="submit"]');
                elements.forEach(el => {
                    const text = el.innerText || el.textContent || el.value;
                    if (text && text.trim()) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) {  // Element is visible
                            clickables.push({
                                tag: el.tagName.toLowerCase(),
                                text: text.trim(),
                                href: el.href || '',
                                id: el.id || '',
                                classes: el.className || ''
                            });
                        }
                    }
                });
                return clickables;
            }
        """)
        return clickables
    
    async def get_ai_action(self):
        """Get next action from Anthropic API based on current state and task"""
        # Create a prompt for the AI to generate the next action
        prompt = f"""
        # Web Automation Task
        
        ## Task Description:
        {self.task_description}
        
        ## Current State:
        - URL: {self.current_state['url']}
        - Page Title: {self.current_state['title']}
        
        ## Visible Elements:
        {json.dumps(self.current_state['visible_text'], indent=2)}
        
        ## Forms:
        {json.dumps(self.current_state['forms'], indent=2)}
        
        ## Clickable Elements:
        {json.dumps(self.current_state['clickable_elements'], indent=2)}
        
        ## Instructions:
        Based on the current page state and the task description, generate Python code using Playwright to perform the next logical action. The code should be a specific, self-contained snippet that will be executed.
        
        The code should:
        1. Take ONE specific action (click, fill form, navigate, etc.)
        2. Be written for async Playwright
        3. Use the variable 'page' which is already defined
        4. Include proper waits for elements or navigation
        5. Not include imports or setup code
        
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
        
        return {
            'action': 'ai_generated',
            'code': code
        }
    
    async def execute_action(self, action_data):
        """Execute the AI-generated code"""
        try:
            # Prepare execution context
            page = self.page
            
            # Format the code with proper indentation
            code = action_data['code']
            
            # Create temporary function with the code
            exec_globals = {'page': page, 'asyncio': asyncio}
            
            # Add debugging info
            print(f"\n--- Executing AI-generated code ---\n{code}\n--------------------------------")
            
            # Create and execute temporary function
            exec(f"async def _temp_action():\n{self._indent_code(code)}", exec_globals)
            await exec_globals['_temp_action']()
            
            # Wait for potential navigation or DOM changes
            await asyncio.sleep(2)
            
            # Add to step history
            self.step_history.append({
                'type': 'ai_action',
                'code': code,
                'timestamp': datetime.datetime.now().isoformat(),
                'url': self.page.url
            })
            
            # Save session after successful step
            await self._save_session()
            
            return {'success': True}
        except Exception as e:
            print(f"Action execution failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    async def execute_user_intervention(self, user_code):
        """Execute user-provided code for intervention"""
        try:
            # Prepare execution context
            page = self.page
            
            # Create temporary function with the code
            exec_globals = {'page': page, 'asyncio': asyncio}
            
            # Add debugging info
            print(f"\n--- Executing user intervention code ---\n{user_code}\n--------------------------------")
            
            # Create and execute temporary function
            exec(f"async def _temp_action():\n{self._indent_code(user_code)}", exec_globals)
            await exec_globals['_temp_action']()
            
            # Wait for potential navigation or DOM changes
            await asyncio.sleep(2)
            
            # Add to step history
            self.step_history.append({
                'type': 'user_intervention',
                'code': user_code,
                'timestamp': datetime.datetime.now().isoformat(),
                'url': self.page.url
            })
            
            # Save session after user intervention
            await self._save_session()
            
            return {'success': True}
        except Exception as e:
            print(f"User intervention failed: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _indent_code(self, code):
        """Add proper indentation to the code"""
        lines = code.split('\n')
        indented_lines = ['    ' + line for line in lines]
        return '\n'.join(indented_lines)
    
    async def run_workflow(self, max_steps=15, start_step=0):
        """Run the complete workflow with AI guidance"""
        if not self.page:
            await self.initialize()
        
        # Start with initial navigation if URL is in the task and this is a new session
        if start_step == 0:
            import re
            urls = re.findall(r'https?://[^\s]+', self.task_description)
            if urls:
                first_url = urls[0]
                print(f"Starting with navigation to {first_url}")
                await self.page.goto(first_url)
                await self.page.wait_for_load_state('networkidle')
        
        # Main control loop
        step_count = start_step
        while step_count < max_steps:
            step_count += 1
            print(f"\n--- Step {step_count} ---")
            
            # Get current state
            state = await self.get_page_state()
            print(f"Current page: {state['title']} ({state['url']})")
            
            # Ask for user intervention if needed
            intervention = await self._check_for_user_intervention()
            if intervention:
                continue
            
            # Get AI-generated action
            next_action = await self.get_ai_action()
            
            # Execute the action
            result = await self.execute_action(next_action)
            
            if not result['success']:
                print(f"Action failed: {result.get('error', 'Unknown error')}")
                error_dir = os.path.join(self.session_dir, f"{self.session_id}_errors")
                if not os.path.exists(error_dir):
                    os.makedirs(error_dir)
                await self.page.screenshot(path=os.path.join(error_dir, f"error_step_{step_count}.png"))
                
                # Ask for user intervention after error
                print("Error encountered. User intervention required.")
                intervention = await self._check_for_user_intervention(True)
                if intervention:
                    continue
                
                # Try to recover with a simple action if no user intervention
                recovery_actions = [
                    "await page.reload()",
                    "await page.goto(page.url)",
                    "await page.wait_for_timeout(3000)"
                ]
                
                print("Attempting recovery...")
                for recovery_code in recovery_actions:
                    try:
                        await eval(recovery_code)
                        print(f"Recovery succeeded with: {recovery_code}")
                        
                        # Add recovery to step history
                        self.step_history.append({
                            'type': 'auto_recovery',
                            'code': recovery_code,
                            'timestamp': datetime.datetime.now().isoformat(),
                            'url': self.page.url
                        })
                        
                        break
                    except:
                        continue
            
            # Ask the AI if the task is complete
            completion_check = await self.check_task_completion()
            if completion_check['is_complete']:
                print(f"Task completed! Reason: {completion_check['reason']}")
                break
        
        if step_count >= max_steps:
            print("Maximum step limit reached. Task may not be complete.")
            await self.page.screenshot(path=os.path.join(self.session_dir, f"{self.session_id}_final.png"))
        
        # Final save before closing
        await self._save_session()
        
    async def _check_for_user_intervention(self, force=False):
        """Check if user wants to intervene"""
        if not force:
            print("\nContinue with AI action? (y/n/c for custom code): ", end="")
        else:
            print("\nUser intervention required. Enter custom code or 'skip' to continue: ", end="")
        
        response = input().strip().lower()
        
        if response == 'n' and not force:
            print("Session paused. You can resume later with the session ID.")
            await self._save_session()
            return True
        elif response == 'c' or (force and response != 'skip'):
            print("Enter custom Playwright code (end with a blank line):")
            lines = []
            while True:
                line = input()
                if line.strip() == "":
                    break
                lines.append(line)
            
            custom_code = "\n".join(lines)
            if custom_code:
                result = await self.execute_user_intervention(custom_code)
                if not result['success']:
                    print(f"Custom code execution failed: {result.get('error')}")
            return True
        
        return False
    
    async def check_task_completion(self):
        """Ask the AI if the task is complete"""
        prompt = f"""
        # Task Completion Check
        
        ## Task Description:
        {self.task_description}
        
        ## Current State:
        - URL: {self.current_state['url']}
        - Page Title: {self.current_state['title']}
        
        ## Visible Elements:
        {json.dumps(self.current_state['visible_text'][:10], indent=2)}
        
        ## Question:
        Based on the task description and current page state, is the task completed?
        
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
    
    async def _save_session(self):
        """Save the current session state for later resuming"""
        if not self.session_id:
            return
        
        # Save browser storage state (cookies, localStorage, etc.)
        storage_path = os.path.join(self.session_dir, f"{self.session_id}_storage.json")
        await self.context.storage_state(path=storage_path)
        
        # Create session data
        session_data = {
            'task_description': self.task_description,
            'last_url': self.page.url,
            'timestamp': datetime.datetime.now().isoformat(),
            'step_history': self.step_history
        }
        
        # Save session data
        session_path = os.path.join(self.session_dir, f"{self.session_id}_data.json")
        with open(session_path, 'w') as f:
            json.dump(session_data, f, indent=2)
        
        print(f"Session saved: {self.session_id}")
        
    def _load_session(self, session_id):
        """Load a saved session"""
        session_path = os.path.join(self.session_dir, f"{session_id}_data.json")
        with open(session_path, 'r') as f:
            session_data = json.load(f)
        return session_data
    
    def _session_exists(self, session_id):
        """Check if a session exists"""
        session_path = os.path.join(self.session_dir, f"{session_id}_data.json")
        storage_path = os.path.join(self.session_dir, f"{session_id}_storage.json")
        return os.path.exists(session_path) and os.path.exists(storage_path)
    
    def list_available_sessions(self):
        """List all available sessions"""
        sessions = []
        for file in os.listdir(self.session_dir):
            if file.endswith("_data.json"):
                session_id = file.rsplit("_data.json", 1)[0]
                session_path = os.path.join(self.session_dir, file)
                
                try:
                    with open(session_path, 'r') as f:
                        session_data = json.load(f)
                        sessions.append({
                            'id': session_id,
                            'timestamp': session_data.get('timestamp', ''),
                            'task': session_data.get('task_description', '')[:50] + '...',
                            'steps_completed': len(session_data.get('step_history', [])),
                            'last_url': session_data.get('last_url', '')
                        })
                except:
                    continue
        
        return sessions
    
    async def close(self):
        """Close the browser and clean up"""
        if self.browser:
            await self.browser.close()