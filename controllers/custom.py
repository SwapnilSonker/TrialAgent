import asyncio
import json
import os
import pickle
import datetime
import textwrap
from playwright.async_api import async_playwright
import anthropic
import subprocess
import tempfile
import re
# from login_handler import LoginHandler

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
        # self.login_handler = LoginHandler(self.page , logger = print)
        
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
        
        # Save the generated script to a file for reference and later use
        script_dir = os.path.join(self.session_dir, f"{self.session_id}_scripts")
        if not os.path.exists(script_dir):
            os.makedirs(script_dir)
        
        script_path = os.path.join(script_dir, f"step_{len(self.step_history) + 1}.py")
        with open(script_path, 'w') as f:
            f.write(f"# Generated script for step {len(self.step_history) + 1}\n")
            f.write(f"# URL: {self.current_state['url']}\n")
            f.write(f"# Timestamp: {datetime.datetime.now().isoformat()}\n\n")
            f.write("async def run(page):\n")
            for line in code.split('\n'):
                f.write(f"    {line}\n")
        
        # Print the script for user visibility
        print("\n--- Generated Playwright Script ---")
        print(code)
        print("--------------------------------")
        print(f"Script saved to: {script_path}")
        
        return {
            'action': 'ai_generated',
            'code': code
        }
        
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
        browser = await playwright.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
""")
            
            # Add each automation step
            for i, step in enumerate(self.step_history):
                if step['type'] in ['ai_action', 'user_intervention', 'codegen_recovery']:
                    f.write(f"\n            # Step {i+1}: {step['type']}\n")
                    
                    # If user manual intervention, add as comment
                    if step['type'] == 'user_manual_intervention':
                        f.write(f"            # Manual intervention: {step['description']}\n")
                        continue
                        
                    # Add the actual code with proper indentation
                    code_lines = step['code'].split('\n')
                    for line in code_lines:
                        f.write(f"            {line}\n")
                    
                    f.write(f"            await page.wait_for_timeout(1000)  # Short delay between actions\n")
            
            # Close everything properly
            f.write("""
                except Exception as e:
                    print(f"Automation failed: {str(e)}")
                    await page.screenshot(path="error.png")
                finally:
                    await browser.close()

# Run the automation
if __name__ == "__main__":
    asyncio.run(run_automation())
""")
        
        print(f"\nFull automation script exported to: {output_path}")
        return output_path        
    
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
    
    async def execute_user_intervention(self, code):
        """Execute user-provided code in the current browser context"""
        result = {'success': False}
        
        try:
            # Create a local namespace with access to the page
            local_ns = {'page': self.page, 'asyncio': asyncio}
            
            # Wrap the code in an async function and execute it
            exec_code = f"""
async def _user_intervention_func(page):
{textwrap.indent(code, '    ')}

async def _run_user_code():
    try:
        await _user_intervention_func(page)
        return {{'success': True}}
    except Exception as e:
        return {{'success': False, 'error': str(e)}}
"""
            exec(exec_code, globals(), local_ns)
            result = await local_ns['_run_user_code']()
            
        except Exception as e:
            result = {'success': False, 'error': str(e)}
        
        # Update step history with the intervention
        self.step_history.append({
            'type': 'user_intervention',
            'code': code,
            'timestamp': datetime.datetime.now().isoformat(),
            'url': self.page.url,
            'success': result['success'],
            'error': result.get('error', None)
        })
        
        # Update page state after intervention
        if result['success']:
            await self.get_page_state()
        
        return result  
     
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
                
                # First try to recover with codegen since this is likely an element not found issue
                print("Attempting recovery with codegen...")
                codegen_success = await self.attempt_codegen_recovery()
                
                if codegen_success:
                    print("Codegen recovery successful, continuing workflow...")
                    continue
                
                # If codegen fails, try simple recovery actions
                recovery_actions = [
                    "await page.reload()",
                    "await page.goto(page.url)",
                    "await page.wait_for_timeout(3000)"
                ]
                
                recovery_succeeded = False
                print("Attempting basic recovery actions...")
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
                        
                        recovery_succeeded = True
                        break
                    except:
                        continue
                
                # If all automatic recovery attempts fail, ask for user intervention
                if not recovery_succeeded:
                    print("All automatic recovery attempts failed. Requesting user intervention...")
                    await self.request_user_intervention()
            
            # Ask the AI if the task is complete
            completion_check = await self.check_task_completion()
            if completion_check['is_complete']:
                print(f"Task completed! Reason: {completion_check['reason']}")
                break
        
        if step_count >= max_steps:
            print("Maximum step limit reached. Task may not be complete.")
            await self.page.screenshot(path=os.path.join(self.session_dir, f"{self.session_id}_final.png"))
        
        # Export the full script before closing
        await self.export_full_script()
        # Final save before closing
        await self._save_session()
    
    async def attempt_codegen_recovery(self):
        """Use Playwright codegen to recover from errors"""
        try:
            print("\n=== RECOVERY WITH CODEGEN ===")
            print("Starting browser recorder to attempt recovery.")
            
            # Create a temporary file to store the generated code
            temp_codegen_file = tempfile.NamedTemporaryFile(delete=False, suffix='.py')
            temp_codegen_path = temp_codegen_file.name
            temp_codegen_file.close()
            
            # Get current URL for the recorder to start from
            current_url = self.page.url
            
            # Use subprocess to call playwright codegen
            print("Starting browser recorder. Complete the action that was failing.")
            print("Close the recorder browser window when you're finished.")
            
            # Launch the codegen process starting at the current URL
            subprocess.run([
                "playwright", "codegen", 
                "--target", "python-async", 
                "--output", temp_codegen_path,
                current_url
            ], check=True)
            
            # Read the generated code
            with open(temp_codegen_path, 'r') as f:
                generated_code = f.read()
            
            # Extract just the relevant action code (remove imports, setup, etc.)
            action_code = ""
            # Look for the code between page.goto and browser.close
            match = re.search(r'page\.goto\([^)]+\)(.*?)# ---------------------', generated_code, re.DOTALL)
            if match:
                action_code = match.group(1).strip()
            else:
                # If not found, look for code between async with and browser.close
                match = re.search(r'async with async_playwright\(\) as playwright:(.*?)await browser\.close\(\)', generated_code, re.DOTALL)
                if match:
                    # Remove the browser setup lines
                    setup_code = match.group(1)
                    action_lines = []
                    capture = False
                    for line in setup_code.split('\n'):
                        if 'page = await context.new_page()' in line:
                            capture = True
                            continue
                        if capture and line.strip() and not line.strip().startswith('#'):
                            action_lines.append(line.strip())
                    action_code = '\n'.join(action_lines)
            
            if not action_code:
                print("No actions were recorded or could be extracted.")
                return False
            
            # Clean up the code further to remove page creation and setup
            action_code = re.sub(r'page = await context\.new_page\(\).*?\n', '', action_code)
            action_code = re.sub(r'await page\.goto\([^)]+\).*?\n', '', action_code)
            
            # Display the extracted code
            print("\n--- Recorded Browser Actions ---")
            print(action_code)
            print("--------------------------------")
            
            # Execute the recorded actions
            result = await self.execute_user_intervention(action_code)
            if not result['success']:
                print(f"Execution of recorded actions failed: {result.get('error')}")
                return False
            
            # Add to step history as codegen recovery
            self.step_history.append({
                'type': 'codegen_recovery',
                'code': action_code,
                'timestamp': datetime.datetime.now().isoformat(),
                'url': current_url
            })
            
            # Update the page state after successful execution
            print("Updating controller with new page state...")
            await self.get_page_state()
            
            print("Codegen recovery successful and saved to script.")
            
            # Clean up temporary file
            try:
                os.unlink(temp_codegen_path)
            except:
                pass
                
            return True
            
        except Exception as e:
            print(f"Error with codegen recovery: {str(e)}")
            return False
    
    async def request_user_intervention(self):
        """Request user intervention when all automatic recovery fails"""
        print("\n=== USER INTERVENTION REQUIRED ===")
        print("Options:")
        print("1. Enter custom code (c)")
        print("2. Use interactive browser mode (i)")
        print("3. Use recorded browser interaction (r)")
        print("Your choice: ", end="")
        
        response = input().strip().lower()
        
        if response == 'c':
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
        elif response == 'i':
            print("\n=== INTERACTIVE BROWSER MODE ===")
            print("Interact with the browser window as needed.")
            print("When done, enter 'd' to continue.")
            
            input("Press Enter when ready to interact with the browser...")
            print("Browser is now available for interaction. When finished:")
            interactive_response = input("Enter 'd' to continue: ").strip().lower()
            
            # Save new page state for script continuation
            print("Updating controller with new page state...")
            await self.get_page_state()
            
            # Add a note in the step history
            self.step_history.append({
                'type': 'user_manual_intervention',
                'description': "Interactive browser mode used for recovery",
                'timestamp': datetime.datetime.now().isoformat(),
                'url': self.page.url
            })
            
            return True
        elif response == 'r':
            # Use Playwright codegen to record user interactions - same as attempt_codegen_recovery
            return await self.attempt_codegen_recovery()
        
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