from .Comfly import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, WEB_DIRECTORY

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS', 'WEB_DIRECTORY']

# (修改后) def start_ai_helper():
# (修改后)     import threading
# (修改后)     import subprocess
# (修改后)     import os
# (修改后)     import sys
# (修改后) 
# (修改后)     def run_ai_helper():
# (修改后)         ai_helper_path = os.path.join(os.path.dirname(__file__), "AiHelper.py")
# (修改后)         subprocess.run([sys.executable, ai_helper_path])
# (修改后) 
# (修改后)     ai_helper_thread = threading.Thread(target=run_ai_helper)
# (修改后)     ai_helper_thread.start()
# (修改后) 
# (修改后) start_ai_helper()

