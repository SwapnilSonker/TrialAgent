import asyncio
import argparse
import os
from controllers.custom import AIControlledAutomation
from dotenv import load_dotenv

load_dotenv()

async def list_sessions(controller):
    """List all saved sessions."""
    sessions = controller.list_available_sessions()
    
    if not sessions:
        print("No saved sessions")
        return 
    
    print("Available sessions:")
    print(f"{'ID': <20} {'Date': <25} {'Steps' : <10} {'Task': < 50}")
    print("-" * 105)
    
    for session in sessions:
        print(f"{session['id']: <20} {session['date']: < 25} {session['timestamp']:<25} {session['steps_completed']:<10} {session['task']}")

async def main():
    parser = argparse.ArgumentParser(description="AI Controlled Automation CLI")
    parser.add_argument('--task' , type=str, help = "Task description")
    parser.add_argument('--api_key' , type = str , help = 'Anthropic API key')
    parser.add_argument('--resume' , type=str ,default=None , help='Resume from session ID')
    parser.add_argument('--list' , action = 'store_true' , help = 'List available sessions')
    parser.add_argument('--max-steps' , type = int , default=15 , help = "Maximum number of steps")
    parser.add_argument('--session_dir'  , type = str,  default = 'sessions' , help = "Directory for sessions storage")
    
    args = parser.parse_args()
    
    api_key = args.api_key or os.environ.get('ANTHROPIC_API_KEY') or os.getenv('ANTHROPIC_API_KEY')    
    if not api_key:
        api_key = input("Please enter your Anthropic API key: ")
        
    task_description = args.task or input("Please enter the task description: ")
    controller = AIControlledAutomation(api_key=api_key, task_description=task_description, session_dir=args.session_dir)
    
    if args.list:
        await list_sessions(controller)
        return
    
    if args.resume:
        print(f"Resuming session {args.resume}")
        if not controller._session_exists(args.resume):
            print(f"Session {args.resume} does not exist.")
            return 
        
        session_data = controller._load_session(args.resume)
        controller.task_description = session_data.get('task_description', " ")
        
        await controller.initialize(args.resume)
        
        start_step = len(controller.step_history)
        print(f"Starting from step{start_step + 1}")
        
        await controller.run_workflow(max_steps=args.max_steps, start_step=start_step)
    else:
        if not args.task:
            args.task = input("Please enter the task description: ")
        controller.task_description = args.task
        await controller.initialize()
        await controller.run_workflow(max_steps=args.max_steps)
        
    await controller.close()
    
if __name__ == "__main__":
    asyncio.run(main())    
        
                