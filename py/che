import tkinter as tk
import socket
import time

def get_local_ip():
    try:
        # 获取本机主机名
        hostname = socket.gethostname()
        # 通过主机名获取 IP 地址
        ip = socket.gethostbyname(hostname)
        return ip
    except Exception as e:
        return "无法获取 IP"

def update_time():
    current_time = time.strftime("%Y-%m-%d %H:%M:%S")
    ip_address = get_local_ip()
    time_label.config(text=f"当前时间: {current_time}\nIP 地址: {ip_address}")
    time_label.after(1000, update_time)  # 每秒更新一次

# 创建窗口
root = tk.Tk()
root.title("时间和IP显示")

# 创建标签来显示时间和IP地址
time_label = tk.Label(root, font=("Arial", 16))
time_label.pack(pady=20)

# 初始显示
update_time()

# 创建关闭按钮
close_button = tk.Button(root, text="关闭", command=root.quit, font=("Arial", 12))
close_button.pack(pady=10)

# 运行主循环
root.mainloop()
