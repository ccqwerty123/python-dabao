import os
import sys

def _append_run_path():
    if getattr(sys, 'frozen', False):
        # 如果是打包后的 exe
        pathlist = []
        
        # 添加程序所在目录
        pathlist.append(os.path.dirname(sys.executable))
        
        # 设置环境变量
        os.environ["PATH"] = ";".join(pathlist) + ";" + os.environ.get("PATH", "")
        
_append_run_path()
