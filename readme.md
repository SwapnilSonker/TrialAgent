to run the project first 

   # First, close ALL Chrome instances
   taskkill /F /IM chrome.exe
   
   # Then launch Chrome with debugging port (use one of these methods):
   # Method 1 - Full path with user data dir
   "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\temp\ChromeDebug"
   