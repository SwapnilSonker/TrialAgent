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
            
    async def extract_all_potential_web_elements(self):
        """Extract all potential UI elements from messaging web applications like WhatsApp, Telegram, etc."""
        web_elements = await self.page.evaluate("""
            () => {
                const result = {
                    // Basic page structure
                    all_headers: [],
                    all_sidebars: [],
                    all_input_areas: [],
                    all_content_containers: [],
                    
                    // Text content 
                    all_navigation_items: [],
                    all_user_elements: [],
                    all_status_indicators: [],
                    
                    // Interactive elements
                    all_buttons: [],
                    all_clickable_items: [],
                    
                    // Messaging-specific elements
                    message_bubbles: [],
                    chat_list_items: [],
                    conversation_threads: [],
                    message_timestamps: [],
                    attachment_buttons: [],
                    emoji_selectors: [],
                    typing_indicators: [],
                    read_receipts: [],
                    media_content_areas: [],
                    
                    // Element counts by attribute
                    element_counts_by_class: {},
                    element_counts_by_data_attr: {},
                    
                    // Page metadata
                    page_title: document.title,
                    viewport_width: window.innerWidth,
                    viewport_height: window.innerHeight
                };
                
                // Extract all text content that might be useful
                const allTextElements = Array.from(document.querySelectorAll('*')).filter(
                    el => el.innerText && el.innerText.trim() && 
                        el.tagName !== 'SCRIPT' && 
                        el.tagName !== 'STYLE'
                );
                
                // Find potential navigation/menu items
                allTextElements.forEach(el => {
                    // Possible navigation items (typically short, in menus, sidebars)
                    if (el.innerText.trim().length < 30) {
                        const parentIsNav = el.closest('nav, [role="navigation"], .nav, .menu, .sidebar');
                        if (parentIsNav) {
                            result.all_navigation_items.push({
                                text: el.innerText.trim(),
                                classes: el.className,
                                id: el.id,
                                tag: el.tagName,
                                attrs: getDataAttributes(el)
                            });
                        }
                    }
                    
                    // Look for user-related elements (avatars, names, profiles)
                    if (el.innerText.trim().length < 40 && !el.innerText.includes('\\n')) {
                        const isUserElement = el.className.toLowerCase().includes('user') || 
                                            el.id.toLowerCase().includes('user') ||
                                            el.closest('[class*="user"], [class*="avatar"], [class*="profile"], [class*="contact"]');
                        if (isUserElement) {
                            result.all_user_elements.push({
                                text: el.innerText.trim(),
                                classes: el.className,
                                id: el.id,
                                tag: el.tagName
                            });
                        }
                    }
                });
                
                // Get potential headers
                document.querySelectorAll('header, [role="banner"], div[class*="header"], div[id*="header"]').forEach(el => {
                    result.all_headers.push({
                        classes: el.className,
                        id: el.id,
                        children_count: el.children.length,
                        text: el.innerText.substring(0, 100)
                    });
                });
                
                // Get potential sidebars (often contains chat lists in messaging apps)
                document.querySelectorAll('aside, nav, div[class*="sidebar"], div[id*="sidebar"], div[class*="nav"], div[id*="nav"], div[class*="chat-list"], div[class*="conversation-list"]').forEach(el => {
                    result.all_sidebars.push({
                        classes: el.className,
                        id: el.id,
                        children_count: el.children.length
                    });
                });
                
                // Get potential input areas (message composers in messaging apps)
                document.querySelectorAll('textarea, [contenteditable="true"], input[type="text"], div[class*="input"], div[class*="editor"], div[class*="composer"], div[class*="message-input"], div[class*="chat-input"], footer textarea').forEach(el => {
                    result.all_input_areas.push({
                        tag: el.tagName,
                        classes: el.className,
                        id: el.id,
                        placeholder: el.getAttribute('placeholder') || '',
                        attrs: getDataAttributes(el)
                    });
                });
                
                // Get potential content containers (message areas in messaging apps)
                document.querySelectorAll('div[class*="content"], div[class*="main"], div[role="main"], main, article, section, div[class*="messages"], div[class*="chat"], div[class*="conversation"]').forEach(el => {
                    result.all_content_containers.push({
                        classes: el.className,
                        id: el.id,
                        children_count: el.children.length
                    });
                });
                
                // Get all clickable elements
                document.querySelectorAll('button, a, [role="button"], [tabindex="0"]').forEach(el => {
                    result.all_buttons.push({
                        tag: el.tagName,
                        classes: el.className,
                        id: el.id,
                        text: el.innerText.trim().substring(0, 50),
                        aria_label: el.getAttribute('aria-label') || '',
                        attrs: getDataAttributes(el)
                    });
                });
                
                // MESSAGING-SPECIFIC ELEMENTS
                
                // Message bubbles - the actual message containers
                document.querySelectorAll('div[class*="message"], div[class*="msg"], div[class*="bubble"], div[class*="chat-item"], [role="message"]').forEach(el => {
                    // Check if it's likely a message bubble (not a container of messages)
                    const isMessageBubble = el.querySelector('div[class*="message"], div[class*="bubble"]') === null || 
                                            el.innerText.length < 1000;
                                            
                    if (isMessageBubble) {
                        const isOutgoing = el.className.includes('out') || 
                                        el.className.includes('sent') || 
                                        el.className.includes('own') ||
                                        el.getAttribute('data-is-outgoing') === 'true';
                        
                        result.message_bubbles.push({
                            text: el.innerText.trim().substring(0, 100),
                            classes: el.className,
                            id: el.id,
                            outgoing: isOutgoing,
                            has_media: !!el.querySelector('img, video, audio, [class*="image"], [class*="video"], [class*="audio"]'),
                            attrs: getDataAttributes(el)
                        });
                    }
                });
                
                // Chat list items (conversations in the sidebar)
                document.querySelectorAll('div[class*="chat-item"], div[class*="conversation"], div[class*="thread"], li[class*="chat"], [role="listitem"]').forEach(el => {
                    // Ensure it's in a sidebar/list context
                    const inListContext = el.closest('[class*="list"], [class*="sidebar"], [role="list"]');
                    
                    if (inListContext) {
                        // Get user name if present
                        const nameEl = el.querySelector('[class*="name"], [class*="title"], strong, b');
                        const name = nameEl ? nameEl.innerText.trim() : '';
                        
                        // Get last message preview if present
                        const previewEl = el.querySelector('[class*="preview"], [class*="snippet"], [class*="last-message"]');
                        const preview = previewEl ? previewEl.innerText.trim().substring(0, 50) : '';
                        
                        // Get unread count if present
                        const unreadEl = el.querySelector('[class*="unread"], [class*="badge"], [class*="count"]');
                        const unreadCount = unreadEl ? unreadEl.innerText.trim() : '';
                        
                        result.chat_list_items.push({
                            name: name,
                            preview: preview,
                            unread_count: unreadCount,
                            classes: el.className,
                            id: el.id,
                            attrs: getDataAttributes(el)
                        });
                    }
                });
                
                // Conversation threads (message container areas)
                document.querySelectorAll('div[class*="conversation"], div[class*="chat"], div[class*="messages"], [role="log"]').forEach(el => {
                    // Filter out sidebar conversation items
                    const isMainChat = !el.closest('[class*="sidebar"], [class*="list"]') && 
                                    el.querySelectorAll('[class*="message"], [class*="bubble"]').length > 0;
                                    
                    if (isMainChat) {
                        result.conversation_threads.push({
                            classes: el.className,
                            id: el.id,
                            message_count: el.querySelectorAll('[class*="message"], [class*="bubble"]').length,
                            attrs: getDataAttributes(el)
                        });
                    }
                });
                
                // Message timestamps
                document.querySelectorAll('[class*="time"], [class*="timestamp"], [class*="date"], time').forEach(el => {
                    const inMessageContext = el.closest('[class*="message"], [class*="bubble"]');
                    if (inMessageContext) {
                        result.message_timestamps.push({
                            text: el.innerText.trim(),
                            classes: el.className,
                            id: el.id,
                            attrs: getDataAttributes(el)
                        });
                    }
                });
                
                // Attachment buttons (for media, files, etc.)
                document.querySelectorAll('button[class*="attach"], [class*="clip"], [class*="file"], button[aria-label*="file"], button[aria-label*="image"], button[aria-label*="photo"], button[aria-label*="attach"]').forEach(el => {
                    result.attachment_buttons.push({
                        classes: el.className,
                        id: el.id,
                        aria_label: el.getAttribute('aria-label') || '',
                        attrs: getDataAttributes(el)
                    });
                });
                
                // Emoji selectors
                document.querySelectorAll('button[class*="emoji"], [class*="smile"], [class*="emotion"], button[aria-label*="emoji"], button[aria-label*="emoticon"], button[aria-label*="sticker"]').forEach(el => {
                    result.emoji_selectors.push({
                        classes: el.className,
                        id: el.id,
                        aria_label: el.getAttribute('aria-label') || '',
                        attrs: getDataAttributes(el)
                    });
                });
                
                // Typing indicators
                document.querySelectorAll('[class*="typing"], [class*="indicator"], [aria-label*="typing"]').forEach(el => {
                    // Check if it's actually a typing indicator (typically contains dots animation)
                    const isTypingIndicator = el.querySelector('[class*="dot"], [class*="ellipsis"]') !== null ||
                                            el.innerText.includes('typing') ||
                                            el.getAttribute('aria-label')?.includes('typing');
                                            
                    if (isTypingIndicator) {
                        result.typing_indicators.push({
                            classes: el.className,
                            id: el.id,
                            text: el.innerText.trim(),
                            attrs: getDataAttributes(el)
                        });
                    }
                });
                
                // Read receipts
                document.querySelectorAll('[class*="tick"], [class*="check"], [class*="read"], [class*="receipt"], [aria-label*="read"], [aria-label*="seen"]').forEach(el => {
                    // Filter to only get read indicators inside or near messages
                    const nearMessage = el.closest('[class*="message"], [class*="bubble"]');
                    if (nearMessage) {
                        result.read_receipts.push({
                            classes: el.className,
                            id: el.id,
                            aria_label: el.getAttribute('aria-label') || '',
                            attrs: getDataAttributes(el)
                        });
                    }
                });
                
                // Media content areas (images, videos, audio messages)
                document.querySelectorAll('img, video, audio, [class*="media"], [class*="image-container"], [class*="voice-message"], [class*="audio-message"]').forEach(el => {
                    // Make sure it's in a message context
                    const inMessageContext = el.closest('[class*="message"], [class*="bubble"]');
                    if (inMessageContext) {
                        const mediaType = el.tagName === 'IMG' ? 'image' : 
                                        el.tagName === 'VIDEO' ? 'video' : 
                                        el.tagName === 'AUDIO' ? 'audio' : 
                                        el.className.includes('voice') ? 'voice' : 'other';
                                        
                        result.media_content_areas.push({
                            type: mediaType,
                            classes: el.className,
                            id: el.id,
                            src: el.getAttribute('src') || '',
                            attrs: getDataAttributes(el)
                        });
                    }
                });
                
                // Status indicators (online status, away, etc.)
                document.querySelectorAll('[class*="status"], [class*="presence"], [class*="online"], [class*="away"], [aria-label*="online"], [aria-label*="status"]').forEach(el => {
                    result.all_status_indicators.push({
                        classes: el.className,
                        id: el.id,
                        text: el.innerText.trim(),
                        aria_label: el.getAttribute('aria-label') || '',
                        attrs: getDataAttributes(el)
                    });
                });
                
                // Analyze data attributes
                document.querySelectorAll('[data-qa], [data-test], [data-testid], [data-key], [data-id]').forEach(el => {
                    const dataAttrs = getDataAttributes(el);
                    Object.keys(dataAttrs).forEach(attr => {
                        const key = `${attr}:${dataAttrs[attr]}`;
                        if (!result.element_counts_by_data_attr[key]) {
                            result.element_counts_by_data_attr[key] = 0;
                        }
                        result.element_counts_by_data_attr[key]++;
                    });
                });
                
                // Helper function to get data attributes
                function getDataAttributes(el) {
                    const result = {};
                    Array.from(el.attributes).forEach(attr => {
                        if (attr.name.startsWith('data-')) {
                            result[attr.name] = attr.value;
                        }
                    });
                    return result;
                }
                
                return result;
            }
        """)
        return web_elements 
    
    async def get_page_state(self):
        """Extract current page information"""
        if not self.page:
            print("Error: No active page. Connect to a browser first.")
            return {
                'url': '',
                'title': '',
                'html': '',
                'visible_text': [],
                'forms': [],
                'clickable_elements': [],
                'platform': 'unknown'
            }  # Return default structure instead of empty dict
        
        try:
            # Re-detect platform each time to handle navigation between platforms
            await self._detect_platform()
            
            # Initialize with default values to prevent "key not found" errors
            current_state = {
                'url': self.page.url,
                'title': await self.page.title(),
                'html': await self.page.content(),
                'visible_text': [],
                'forms': [],
                'clickable_elements': [],
                'platform': self.platform
            }
            
            # Try to add each component, but continue if any fails
            try:
                current_state['visible_text'] = await self.extract_visible_text()
            except Exception as e:
                print(f"Error extracting visible text: {str(e)}")
                
            try:
                current_state['forms'] = await self.detect_forms()
            except Exception as e:
                print(f"Error detecting forms: {str(e)}")
                
            try:
                current_state['clickable_elements'] = await self.detect_clickable_elements()
            except Exception as e:
                print(f"Error detecting clickable elements: {str(e)}")
            
            # Add popup detection
            # try:
                # current_state['popups'] = await self.detect_popups()
            # except Exception as e:
            # print(f"Error detecting popups: {str(e)}")
            # current_state['popups'] = {'popups': []}
            
            # Add platform-specific data
            try:
                if self.platform == "notion":
                    current_state['platform_specific'] = await self.extract_notion_specific_elements()
                elif self.platform == "slack":
                    current_state['platform_specific'] = await self.extract_slack_specific_elements()
                else :
                    current_state['platform_specific'] = await self.extract_all_potential_web_elements()  
                    # print(f" discord logs : {current_state['platform_specific']}")  
            except Exception as e:
                print(f"Error extracting platform-specific elements: {str(e)}")
                current_state['platform_specific'] = {}
            
            # Take a screenshot for reference
            try:
                screenshots_dir = os.path.join(self.session_dir, f"{self.session_id}_screenshots")
                if not os.path.exists(screenshots_dir):
                    os.makedirs(screenshots_dir)
                
                screenshot_path = os.path.join(screenshots_dir, f"step_{len(self.step_history) + 1}.png")
                await self.page.screenshot(path=screenshot_path)
            except Exception as e:
                print(f"Error taking screenshot: {str(e)}")
            
            # Save current state to a file for state persistence
            try:
                self._save_current_state(current_state)
            except Exception as e:
                print(f"Error saving current state: {str(e)}")
            
            return current_state
            
        except Exception as e:
            print(f"Error getting page state: {str(e)}")
            return {
                'url': '',
                'title': '',
                'html': '',
                'visible_text': [],
                'forms': [],
                'clickable_elements': [],
                'platform': 'unknown'
            }  # Return default structure    
                  
    def _save_current_state(self, state):
        """Save the current state to a file for recovery"""
        states_dir = os.path.join(self.session_dir, f"{self.session_id}_states")
        if not os.path.exists(states_dir):
            os.makedirs(states_dir)
        
        # Don't save the full HTML to avoid massive files
        state_to_save = state.copy()
        if 'html' in state_to_save:
            state_to_save['html'] = "HTML content omitted for file size"
        
        state_path = os.path.join(states_dir, f"state_{len(self.step_history)}.json")
        with open(state_path, 'w') as f:
            json.dump(state_to_save, f, indent=2, default=str)

    def _load_last_state(self):
        """Load the most recent saved state"""
        states_dir = os.path.join(self.session_dir, f"{self.session_id}_states")
        if not os.path.exists(states_dir):
            return None
        
        states = [f for f in os.listdir(states_dir) if f.startswith("state_") and f.endswith(".json")]
        if not states:
            return None
        
        # Get the latest state file
        latest_state = sorted(states, key=lambda x: int(x.split("_")[1].split(".")[0]))[-1]
        state_path = os.path.join(states_dir, latest_state)
        
        with open(state_path, 'r') as f:
            return json.load(f)
        
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
        """Detect forms and input fields on the page"""
        try:
            forms = await self.page.evaluate("""
                () => {
                    const result = [];
                    // Get all forms
                    document.querySelectorAll('form').forEach((form, formIndex) => {
                        const formData = {
                            id: form.id || `form_${formIndex}`,
                            action: form.action || '',
                            method: form.method || '',
                            inputs: []
                        };
                        
                        // Get all inputs in this form
                        form.querySelectorAll('input, select, textarea').forEach((input, inputIndex) => {
                            formData.inputs.push({
                                name: input.name || '',
                                id: input.id || '',
                                type: input.type || input.tagName.toLowerCase(),
                                value: input.value || '',
                                placeholder: input.placeholder || '',
                                required: input.required || false
                            });
                        });
                        
                        result.push(formData);
                    });
                    
                    // Also detect standalone input fields (not in forms)
                    const standaloneForm = {
                        id: 'standalone_inputs',
                        action: '',
                        method: '',
                        inputs: []
                    };
                    
                    document.querySelectorAll('input:not(form input), textarea:not(form textarea), select:not(form select), [contenteditable="true"]').forEach((input, index) => {
                        standaloneForm.inputs.push({
                            name: input.name || '',
                            id: input.id || '',
                            type: input.type || input.tagName.toLowerCase() || (input.hasAttribute('contenteditable') ? 'contenteditable' : ''),
                            value: input.value || '',
                            placeholder: input.placeholder || '',
                            required: input.required || false
                        });
                    });
                    
                    if (standaloneForm.inputs.length > 0) {
                        result.push(standaloneForm);
                    }
                    
                    return result;
                }
            """)
            return forms
        except Exception as e:
            print(f"Error detecting forms: {str(e)}")
            return []  # Return an empty list instead of None or raising an error  
        
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
        """Get next action from Anthropic API with enhanced context understanding"""
        # Update platform detection if needed
        await self._detect_platform()
        
        # Create a more detailed prompt with explicit context
        prompt = f"""
        # Advanced Web Automation for {self.platform.capitalize()}
        
        ## Task Description:
        {self.task_description}
        
        ## Current Context:
        - Platform: {self.platform}
        - URL: {current_state['url']}
        - Page Title: {current_state['title']}
        - Current Step: {len(self.step_history) + 1}
        
        ## Previous Actions (Last 3):
        {self._format_previous_actions()}
        
        ## Current Page Analysis:
        1. Popups/Dialogs: {len(current_state.get('popups', {}).get('popups', []))} detected
        2. Forms Present: {len(current_state['forms'])}
        3. Clickable Elements: {min(len(current_state['clickable_elements']), 30)} detected
        
        ## Platform-Specific Context:
        {json.dumps(current_state.get('platform_specific', {}), indent=2)}
        
        ## Decision-Making Instructions:
        1. CAREFULLY ANALYZE the current page state in relation to the task
        2. IDENTIFY the optimal next action that progresses toward task completion
        3. HANDLE any popups or dialogs first before other interactions
        4. PRIORITIZE direct task-related interactions over exploration
        5. DETERMINE if you need to:
        - Fill forms with appropriate values
        - Click specific buttons or links
        - Navigate to new areas
        - Extract content
        - Scroll or move to view more content
        6. CONSIDER the task context and previous steps when deciding the next action
        7. ALWAYS USE MULTIPLE SELECTOR STRATEGIES for each element:
            - Try CSS selector first
            - Fall back to XPath as alternative
            - Use text content as last resort
            - Wait for elements to be visible AND enabled before interaction
            - Do not go far from my task that I have alloted you to do
        
        ## Critical Page Elements:
        - Popups: {json.dumps(current_state.get('popups', {}).get('popups', [])[:3], indent=2)}
        - Forms: {json.dumps(current_state['forms'][:2], indent=2)}
        - Key Clickable Elements: {json.dumps(current_state['clickable_elements'][:15], indent=2)}
        - Key Text Elements: {json.dumps(current_state['visible_text'][:15], indent=2)}
        
        ## Generate high-quality Python code for the SINGLE most logical next action:
        - Use async Playwright syntax with the existing 'page' variable
        - Include appropriate waits (waitForSelector, waitForNavigation, etc.)
        - Use multiple selector strategies (CSS, XPath, text, etc.) for reliability
        - Add error handling with try/except blocks
        - Include detailed inline comments explaining the action and its purpose
        - Ensure proper timing between actions with waits
        
        Generate ONLY executable Python code without any explanations, markdown, or surrounding text.
        """
        
        # Call the Anthropic API with increased tokens for deeper analysis
        response = self.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1500,
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
        
        # Add additional error handling to the code
        enhanced_code = self._enhance_code_with_error_handling(code)
        # print(f"current state gen : {current_state}")
        # Save the generated script with timestamp and context
        script_dir = os.path.join(self.session_dir, f"{self.session_id}_scripts")
        if not os.path.exists(script_dir):
            os.makedirs(script_dir)
        
        script_path = os.path.join(script_dir, f"step_{len(self.step_history) + 1}.py")
        with open(script_path, 'w', encoding="utf-8") as f:
            f.write(f"# Generated script for step {len(self.step_history) + 1}\n")
            f.write(f"# Task: {self.task_description}\n")
            f.write(f"# Platform: {self.platform}\n")
            f.write(f"# URL: {current_state['url']}\n")
            f.write(f"# Page Title: {current_state.get('title', 'Untitled')}\n")
            f.write(f"# Timestamp: {datetime.datetime.now().isoformat()}\n\n")
            f.write("async def run(page):\n")
            for line in enhanced_code.split('\n'):
                f.write(f"    {line}\n")
        
        # Get explanation for the action
        explanation = await self._get_action_explanation(enhanced_code)
        
        return {
            'code': enhanced_code,
            'explanation': explanation,
            'script_path': script_path
        } 
        
    
    def _enhance_code_with_error_handling(self, code):
        """Add improved error handling to generated code"""
        # Add general try/except if not already present
        if "try:" not in code:
            lines = code.split('\n')
            enhanced_lines = ["try:"]
            for line in lines:
                enhanced_lines.append("    " + line)
            
            enhanced_lines.extend([
                "except Exception as e:",
                "    print(f\"Action failed with error: {str(e)}\")",
                "    # Take screenshot of error state",
                "    await page.screenshot(path=f\"error_state_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png\")"
            ])
            
            return '\n'.join(enhanced_lines)
        
        return code    
        
    async def _get_action_explanation(self, code):
        """Get a human-friendly explanation of what the code will do"""
        prompt = f"""
        The following is Python code for a web automation action:
        
        ```python
        {code}
        ```
        
        Please explain what this code will do in 1-2 simple sentences, focusing on the user-facing action.
        Be specific about what elements will be interacted with.
        
        Return ONLY the explanation, no additional text.
        """
        
        response = self.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}]
        )
        
        return response.content[0].text.strip()    
    
    def _format_previous_actions(self):
        """Format previous actions for context in prompts"""
        if not self.step_history:
            return "No previous actions taken."
        
        recent_actions = self.step_history[-min(len(self.step_history), 3):]
        formatted = []
        
        for i, action in enumerate(recent_actions):
            step_num = len(self.step_history) - len(recent_actions) + i + 1
            code_summary = action.get('code', '')
            # Extract first 2-3 lines for brevity
            code_lines = code_summary.split('\n')[:3]
            code_preview = '\n'.join(code_lines)
            if len(code_lines) < len(code_summary.split('\n')):
                code_preview += "\n..."
                
            formatted.append(f"Step {step_num}: {code_preview}")
        
        return "\n".join(formatted)    
    
    async def chat_query(self, query):
        """Handle conversational queries about the current page state"""
        current_state = await self.get_page_state()
        if not current_state:
            return "Unable to get current page state."
            
        # Create a prompt for the AI to answer the query based on current state
        prompt = f"""
        # Web Page Analysis Query

        ## Current State:
        - Platform: {self.platform}
        - URL: {current_state['url']}
        - Page Title: {current_state['title']}
        
        ## Detected Popups:
        {json.dumps(current_state.get('popups', {}), indent=2)}
        
        ## Platform-Specific Elements:
        {json.dumps(current_state.get('platform_specific', {}), indent=2)}
        
        ## Visible Text Elements:
        {json.dumps(current_state['visible_text'][:30], indent=2)}
        
        ## Clickable Elements:
        {json.dumps(current_state['clickable_elements'][:30], indent=2)}
        
        ## Forms:
        {json.dumps(current_state['forms'], indent=2)}
        
        ## User Query:
        {query}
        
        Based on the current page state, answer the user's query conversationally.
        Focus on providing specific information from the extracted page data.
        """
        
        # Call the Anthropic API
        response = self.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        
        # Return the response
        answer = response.content[0].text.strip()
        return answer
    
    async def execute_action(self, code):
        """Execute the AI-generated code with improved error handling and feedback"""
        if not self.page:
            print("Error: No active page. Connect to a browser first.")
            return {'success': False, 'error': 'No active page'}
        
        
        try:
            # Check for popups before executing the action
            # current_state = await self.get_page_state()
            # popups = current_state.get('popups', {}).get('popups', [])
            
            # if popups:
            #     print(f"\n--- Detected {len(popups)} popup(s) ---")
            #     for i, popup in enumerate(popups):
            #         popup_text = popup.get('text', '')[:50].replace('\n', ' ')
            #         print(f"Popup {i+1}: {popup_text}...")
                    
            #         if popup.get('buttons'):
            #             print(f"  Buttons: {', '.join(popup['buttons'][:3])}")
                
                # Get AI guidance on how to handle the popup
                # popup_handling_code = await self.get_popup_handling_action(popups)
                
                # Execute the popup handling code
                # print("Handling popup before proceeding...")
                # page = self.page
                # exec_globals = {'page': page, 'asyncio': asyncio, 'datetime': datetime}
                # exec(f"async def _handle_popup():\n{self._indent_code(popup_handling_code)}", exec_globals)
                # await exec_globals['_handle_popup']()
                
                # Wait for popup to be dismissed
                # await asyncio.sleep(2)
            
            # Prepare execution context for the main action
            page = self.page
            exec_globals = {'page': page, 'asyncio': asyncio, 'datetime': datetime}
            
            # Add debugging info
            print(f"\n--- Executing AI-generated code on {self.platform.capitalize()} ---")
            
            max_retries = 3
            retry_count = 0
            while retry_count < max_retries:
                try:
                    # Execute code here
                    exec(f"async def _temp_action():\n{self._indent_code(code)}", exec_globals)
                    await exec_globals['_temp_action']()
                    break  # Success, exit retry loop
                except Exception as e:
                    retry_count += 1
                    print(f"Attempt {retry_count}/{max_retries} failed: {str(e)}")
                    if retry_count < max_retries:
                        print("Retrying after short delay...")
                        await asyncio.sleep(2)
                    else:
                        raise  # Re-raise if all retries failed
            
            # Take screenshot before execution
            before_screenshot = f"before_step_{len(self.step_history) + 1}.png"
            await self.page.screenshot(path=os.path.join(self.session_dir, before_screenshot))
            
            # Create and execute temporary function
            exec(f"async def _temp_action():\n{self._indent_code(code)}", exec_globals)
            await exec_globals['_temp_action']()
            
            # Wait for potential navigation or DOM changes
            await asyncio.sleep(5)
            
            # Take screenshot after execution
            after_screenshot = f"after_step_{len(self.step_history) + 1}.png"
            await self.page.screenshot(path=os.path.join(self.session_dir, after_screenshot))
            
            # Add to step history with more details
            self.step_history.append({
                'type': 'ai_action',
                'platform': self.platform,
                'code': code,
                'timestamp': datetime.datetime.now().isoformat(),
                'url': self.page.url,
                'title': await self.page.title(),
                'before_screenshot': before_screenshot,
                'after_screenshot': after_screenshot
            })
            
            return {'success': True}
        except Exception as e:
            error_message = str(e)
            print(f"Action execution failed: {error_message}")
            
            # Take error screenshot
            error_screenshot = f"error_step_{len(self.step_history) + 1}.png"
            await self.page.screenshot(path=os.path.join(self.session_dir, error_screenshot))
            
            return {
                'success': False, 
                'error': error_message,
                'error_screenshot': error_screenshot
            }  
    
    async def analyze_task_completion(self, current_state):
        """Analyze whether the task has been completed with detailed reasoning"""
        prompt = f"""
        # Task Completion Analysis for {self.platform.capitalize()}
        
        ## Task Description:
        {self.task_description}
        
        ## Current State:
        - Platform: {self.platform}
        - URL: {current_state['url']}
        - Page Title: {current_state['title']}
        
        ## Steps Executed:
        {self._format_complete_history()}
        
        ## Platform-Specific Elements:
        {json.dumps(current_state.get('platform_specific', {}), indent=2)}
        
        ## Current Page Content (Sample):
        {json.dumps(current_state['visible_text'][:20], indent=2)}
        
        ## Analysis Request:
        Based on the task description and current page state, perform a detailed analysis:
        
        1. Is the task fully completed? Consider all requirements in the task description.
        2. What evidence in the current page state indicates completion or non-completion?
        3. Are there any subtasks that remain to be done?
        4. Is the current page state what we would expect if the task was completed?
        
        Return a JSON object with the following fields:
        1. "is_complete": true or false
        2. "completion_percentage": estimated percentage of task completed (0-100)
        3. "reason": detailed explanation of your analysis
        4. "remaining_steps": list of any remaining steps needed (empty if complete)
        
        Only return the JSON object, nothing else.
        """
        
        response = self.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=800,
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
        except Exception as e:
            print(f"Error parsing task completion analysis: {str(e)}")
            # If parsing fails, return a default response
            return {
                'is_complete': False,
                'completion_percentage': 0,
                'reason': "Unable to determine completion status due to parsing error",
                'remaining_steps': ["Continue with the task"]
            }
        
    def _format_complete_history(self):
        """Format the complete step history for analysis"""
        if not self.step_history:
            return "No steps executed yet."
        
        formatted = []
        for i, step in enumerate(self.step_history):
            step_summary = f"Step {i+1}: "
            if 'explanation' in step:
                step_summary += step['explanation']
            else:
                # Extract first line of code as summary
                code_lines = step.get('code', '').split('\n')
                if code_lines:
                    step_summary += code_lines[0].strip()
                else:
                    step_summary += "Unknown action"
                    
            formatted.append(step_summary)
        
        return "\n".join(formatted)
            
    async def run_chat_interface(self):
        """Run an improved chat-based interface for the automation"""
        print("\n=== Web Automation Assistant ===")
        print(f"Connected to: {await self.page.title()} ({self.page.url})")
        print(f"Detected platform: {self.platform}")
        
        # Get more detailed information about the current page
        current_state = await self.get_page_state()
        # print(f"current state : {current_state}")
        page_elements = {
            'forms': len(current_state['forms']),
            'clickables': len(current_state['clickable_elements']),
            'popups': len(current_state.get('popups', {}).get('popups', []))
        }
        
        print(f"\nAnalysis: Detected {page_elements['forms']} forms, {page_elements['clickables']} clickable elements, and {page_elements['popups']} popups")
        print("\nI'm your web automation assistant. I can help you automate tasks or answer questions about this page.")
        print("What would you like to do? (Type 'help' for commands)")
        
        while True:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("Assistant: Goodbye! Closing automation assistant.")
                break
                    
            if user_input.lower() in ['help', 'commands']:
                print("\nAssistant: Here are available commands:")
                print("- 'automate [task]': Start automating a specific task")
                print("- 'next step': Execute the next automation step")
                print("- 'continue [n]': Run n automation steps (default: 3)")
                print("- 'state': Get analysis of the current page")
                print("- 'screenshot': Take a screenshot of the current page")
                print("- 'save script': Export the full automation script")
                print("- 'analyze completion': Analyze if the task is complete")
                print("- 'go to [url]': Navigate to a specific URL")
                print("- Any other input will be treated as a question about the page")
                continue
                    
            # Update state to ensure we have the latest information
            current_state = await self.get_page_state()
            
            # Handle different command types
            if user_input.lower().startswith('automate '):
                # Set a new task and prepare for automation
                self.task_description = user_input[9:].strip()
                print(f"\nAssistant: I'll help you automate: {self.task_description}")
                print("I'm analyzing the page to determine the best course of action...")
                # print(f"current state : {current_state}")
                # Generate the first action but don't execute yet
                action_data = await self.get_ai_action(current_state)
                print(f"\nAssistant: Next step - {action_data['explanation']}")
                print("Type 'next step' to execute this action.")
                self.pending_action = action_data
                
            elif user_input.lower() == 'next step':
                # Execute pending action if available
                if hasattr(self, 'pending_action') and self.pending_action:
                    print(f"\nAssistant: Executing step - {self.pending_action['explanation']}...")
                    result = await self.execute_action(self.pending_action['code'])
                    
                    if result['success']:
                        print("Action completed successfully!")
                        # Get updated state
                        current_state = await self.get_page_state()
                        
                        # Check if task is complete
                        completion = await self.analyze_task_completion(current_state)
                        if completion['is_complete']:
                            print(f"\nTask completed! ({completion['completion_percentage']}%)")
                            print(f"Reason: {completion['reason']}")
                            
                            # Save the complete automation script
                            script_path = await self.export_full_script()
                            print(f"Full automation script saved to: {script_path}")
                            
                            self.pending_action = None
                        else:
                            # Generate next action
                            self.pending_action = await self.get_ai_action(current_state)
                            print(f"\nAssistant: Next step - {self.pending_action['explanation']}")
                            print(f"Progress: ~{completion['completion_percentage']}% complete")
                    else:
                        print(f"Action failed: {result.get('error', 'Unknown error')}")
                        if 'error_screenshot' in result:
                            print(f"Error screenshot saved to: {result['error_screenshot']}")
                        
                        # Ask for recovery options
                        print("\nAssistant: I encountered an issue. What would you like to do?")
                        print("1. Try again")
                        print("2. Get a new suggestion")
                        print("3. Manual intervention (I'll wait)")
                        recovery_choice = input("Enter choice (1-3): ")
                        
                        if recovery_choice == '1':
                            # Try the same action again
                            print("Trying the same action again...")
                            result = await self.execute_action(self.pending_action['code'])
                            if result['success']:
                                print("Success on retry!")
                                current_state = await self.get_page_state()
                                self.pending_action = await self.get_ai_action(current_state)
                                print(f"\nAssistant: Next step - {self.pending_action['explanation']}")
                        elif recovery_choice == '2':
                            # Get a new action suggestion
                            print("Getting a new action suggestion...")
                            current_state = await self.get_page_state()
                            self.pending_action = await self.get_ai_action(current_state)
                            print(f"\nAssistant: New suggested step - {self.pending_action['explanation']}")
                        else:
                            # Manual intervention
                            print("Please manually interact with the browser, then type 'next step' when ready")
                            await asyncio.sleep(1)
                            self.pending_action = None
                else:
                    print("\nAssistant: No pending action. Use 'automate [task]' to start a new task.")
            
            # Add the remaining handlers for other commands...
            # (The rest of the method would handle the remaining commands like 'continue',
            # 'state', 'screenshot', 'save script', etc. - I'm focusing on the core functionality)
            
            elif user_input.lower().startswith('continue'):
                # [Implementation of continue command]
                parts = user_input.split()
                steps = 3  # Default
                if len(parts) > 1 and parts[1].isdigit():
                    steps = int(parts[1])
                    
                print(f"\nAssistant: Running {steps} automation steps...")
                
                for i in range(steps):
                    if not hasattr(self, 'pending_action') or not self.pending_action:
                        # Generate a new action if none is pending
                        self.pending_action = await self.get_ai_action(current_state)
                        
                    print(f"\nStep {i+1}/{steps} - {self.pending_action['explanation']}...")
                    result = await self.execute_action(self.pending_action['code'])
                    
                    if result['success']:
                        print("Success!")
                        # Update state and generate next action
                        current_state = await self.get_page_state()
                        
                        # Check if task is complete
                        completion = await self.analyze_task_completion(current_state)
                        if completion['is_complete']:
                            print(f"\nTask completed! ({completion['completion_percentage']}%)")
                            print(f"Reason: {completion['reason']}")
                            script_path = await self.export_full_script()
                            print(f"Full automation script saved to: {script_path}")
                            self.pending_action = None
                            break
                        
                        self.pending_action = await self.get_ai_action(current_state)
                    else:
                        print(f"Step failed: {result.get('error', 'Unknown error')}")
                        print("\nEncountered an error. Stopping automation sequence.")
                        break
                        
                print("\nAssistant: Automation sequence completed.")
                if hasattr(self, 'pending_action') and self.pending_action:
                    print(f"Next suggested step: {self.pending_action['explanation']}")
                    
            elif user_input.lower() == 'save script':
                script_path = await self.export_full_script()
                print(f"\nAssistant: Full automation script saved to: {script_path}")
                
            elif user_input.lower() == 'analyze completion':
                completion = await self.analyze_task_completion(current_state)
                print(f"\nAssistant: Task Completion Analysis:")
                print(f"Complete: {completion['is_complete']}")
                print(f"Progress: ~{completion['completion_percentage']}% complete")
                print(f"Analysis: {completion['reason']}")
                if completion['remaining_steps']:
                    print("Remaining steps:")
                    for i, step in enumerate(completion['remaining_steps']):
                        print(f"  {i+1}. {step}")
                        
            elif user_input.lower().startswith('go to '):
                url = user_input[6:].strip()
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                print(f"\nAssistant: Navigating to {url}...")
                try:
                    await self.page.goto(url)
                    await asyncio.sleep(2)
                    await self._detect_platform()
                    current_state = await self.get_page_state()
                    print(f"Navigation complete. Now at: {current_state['title']}")
                    print(f"Platform detected: {self.platform}")
                except Exception as e:
                    print(f"Navigation failed: {str(e)}")
                    
            else:
                # Treat as a general question about the page
                answer = await self.chat_query(user_input)
                print(f"\nAssistant: {answer}")
                              
    def _indent_code(self, code):
        """Add proper indentation to the code"""
        lines = code.split('\n')
        indented_lines = ['    ' + line for line in lines]
        return '\n'.join(indented_lines)
    
    async def get_popup_handling_action(self, popups):
        """Get AI-generated code to handle detected popups"""
        prompt = f"""
        # Popup Handling for {self.platform.capitalize()}
        
        ## Detected Popups:
        {json.dumps(popups, indent=2)}
        
        ## Instructions:
        Generate Python code using Playwright to handle the detected popup(s). The code should:
        1. Target the popup(s) using appropriate selectors
        2. Either close the popup(s) or interact with them as needed
        3. Be written for async Playwright
        4. Use the variable 'page' which is already defined
        5. Include proper waits for elements
        
        Generate ONLY executable Python code without any explanations or markdown. The code will be directly executed.
        """
        
        # Call the Anthropic API
        response = self.client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=800,
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
        
        script_path = os.path.join(script_dir, f"popup_handler_{len(self.step_history) + 1}.py")
        with open(script_path, 'w') as f:
            f.write(f"# Generated popup handling script\n")
            f.write(f"# Platform: {self.platform}\n")
            f.write(f"# Timestamp: {datetime.datetime.now().isoformat()}\n\n")
            f.write("async def run(page):\n")
            for line in code.split('\n'):
                f.write(f"    {line}\n")
        
        # Print the script for user visibility
        print(f"\n--- Generated Popup Handling Script ---")
        print(code)
        print("--------------------------------")
        
        return code
     
    async def detect_popups(self):
        """Detect popups, modals, and dialogs on the page with improved accuracy"""
        popups = await self.page.evaluate("""
            () => {
                const result = {
                    popups: []
                };
                
                // Enhanced popup selectors including aria attributes
                const popupSelectors = [
                    // Common modal selectors
                    '.modal', '[role="dialog"]', '.popup', '.overlay', '.dialog',
                    // Aria-based selectors
                    '[aria-modal="true"]', '[aria-haspopup="dialog"]', 
                    // Platform-specific selectors
                    '.notion-overlay-container', '.c-dialog__content', '.ReactModal__Content',
                    // Elements with modal/popup/dialog in attribute values
                    '[class*="modal"]', '[class*="popup"]', '[class*="dialog"]',
                    '[id*="modal"]', '[id*="popup"]', '[id*="dialog"]',
                    // Elements with high z-index that might be popups
                    '[style*="z-index:"]'
                ];
                
                // Check each selector
                popupSelectors.forEach(selector => {
                    try {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            // Improved visibility check
                            const style = window.getComputedStyle(el);
                            const rect = el.getBoundingClientRect();
                            const isVisible = style.display !== 'none' && 
                                            style.visibility !== 'hidden' && 
                                            style.opacity !== '0' &&
                                            rect.width > 10 && 
                                            rect.height > 10 &&
                                            rect.top >= 0 &&
                                            rect.left >= 0;
                            
                            if (isVisible) {
                                const text = el.innerText || el.textContent;
                                const buttons = Array.from(el.querySelectorAll('button, [role="button"]'))
                                    .map(btn => btn.innerText || btn.textContent || btn.value || btn.getAttribute('aria-label') || '');
                                
                                result.popups.push({
                                    selector: selector,
                                    text: text ? text.trim().substring(0, 200) : '',
                                    buttons: buttons.filter(btn => btn.trim()),
                                    position: {
                                        top: rect.top,
                                        left: rect.left,
                                        width: rect.width,
                                        height: rect.height
                                    },
                                    hasCloseButton: !!el.querySelector('button[aria-label*="close"], [aria-label*="Close"], .close, .close-button, .dismiss, button[aria-label*="dismiss"], [class*="close"], [id*="close"]')
                                });
                            }
                        });
                    } catch (e) {
                        // Ignore errors for individual selectors
                    }
                });
                
                return result;
            }
        """)
        return popups
    
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
    
    # Create the automation instance with an initial empty task
    automation = WebAutomation("", api_key)
    
    # Connect to existing browser session
    print("\n=== Web Automation Assistant ===")
    print("Connecting to browser...")
    connection_successful = await automation.connect_to_existing_browser(debugging_port=9222)
    if not connection_successful:
        print("Failed to connect to browser. Make sure Chrome is running with remote debugging enabled.")
        print("Launch Chrome with: chrome.exe --remote-debugging-port=9222")
        return
    
    # Start the chat interface
    await automation.run_chat_interface()
    
    # Clean up
    await automation.close()
    
if __name__ == "__main__":
    asyncio.run(main())