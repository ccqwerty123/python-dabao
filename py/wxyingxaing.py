import tkinter as tk
from tkinter import ttk, messagebox
import qrcode
from PIL import Image, ImageTk
import socket
import threading
import soundcard as sc
import numpy as np
import queue
import struct
import random
import string
import jwt
import time
import winsound  # 用于测试音频
from flask import Flask, Response, request
from datetime import datetime, timedelta

class AudioStreamer:
    def __init__(self):
        self.app = Flask(__name__)
        self.audio_queue = queue.Queue(maxsize=50)
        self.connected_clients = {}
        self.password = self.generate_password()
        self.secret_key = self.generate_password(16)
        self.max_clients = 1
        self.is_recording = False
        
        # 音频参数
        self.CHANNELS = 2
        self.RATE = 44100
        self.CHUNK = 1024
        
        # 获取所有音频设备
        self.audio_devices = self.get_audio_devices()
        self.selected_device = None
        
        self.setup_routes()
        self.setup_gui()

    def get_audio_devices(self):
        """获取所有音频输出设备"""
        speakers = sc.all_speakers()
        return {str(speaker): speaker for speaker in speakers}

    def setup_gui(self):
        """设置图形界面"""
        self.root = tk.Tk()
        self.root.title("音频流服务器")
        self.root.geometry("500x850")  # 增加窗口高度以容纳新控件

        # 样式设置
        style = ttk.Style()
        style.configure('TLabel', font=('Arial', 10))
        style.configure('Header.TLabel', font=('Arial', 12, 'bold'))

        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 设备选择框架
        device_frame = ttk.LabelFrame(main_frame, text="音频设备设置", padding="5")
        device_frame.pack(fill=tk.X, pady=5)

        # 设备选择下拉框
        ttk.Label(device_frame, text="选择音频设备：").pack(fill=tk.X)
        self.device_var = tk.StringVar()
        self.device_dropdown = ttk.Combobox(device_frame, 
                                          textvariable=self.device_var,
                                          values=list(self.audio_devices.keys()))
        self.device_dropdown.pack(fill=tk.X, pady=5)
        self.device_dropdown.bind('<<ComboboxSelected>>', self.on_device_select)

        # 设备控制按钮框架
        device_control_frame = ttk.Frame(device_frame)
        device_control_frame.pack(fill=tk.X, pady=5)

        # 测试按钮
        self.test_button = ttk.Button(device_control_frame, 
                                    text="测试设备", 
                                    command=self.test_device,
                                    state='disabled')
        self.test_button.pack(side=tk.LEFT, padx=5)

        # 启动/停止按钮
        self.start_button = ttk.Button(device_control_frame, 
                                     text="启动录制", 
                                     command=self.toggle_recording,
                                     state='disabled')
        self.start_button.pack(side=tk.LEFT, padx=5)

        # 设备状态标签
        self.device_status_var = tk.StringVar(value="状态：未选择设备")
        ttk.Label(device_frame, textvariable=self.device_status_var).pack()

        # 用户限制设置
        limit_frame = ttk.LabelFrame(main_frame, text="用户限制", padding="5")
        limit_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(limit_frame, text="最大连接数：").pack(side=tk.LEFT)
        self.max_clients_var = tk.StringVar(value="1")
        spinbox = ttk.Spinbox(
            limit_frame, 
            from_=1, 
            to=10, 
            width=5,
            textvariable=self.max_clients_var,
            command=self.update_max_clients
        )
        spinbox.pack(side=tk.LEFT, padx=5)

        # 加密直接访问链接
        direct_frame = ttk.LabelFrame(main_frame, text="加密直接访问", padding="5")
        direct_frame.pack(fill=tk.X, pady=5)
        
        self.direct_url_var = tk.StringVar()
        ttk.Entry(direct_frame, textvariable=self.direct_url_var, state='readonly').pack(fill=tk.X, pady=5)
        ttk.Button(direct_frame, text="复制链接", command=lambda: self.copy_text(self.direct_url_var.get())).pack()

        # 密码访问信息
        pwd_frame = ttk.LabelFrame(main_frame, text="密码访问", padding="5")
        pwd_frame.pack(fill=tk.X, pady=5)
        
        self.pwd_url_var = tk.StringVar()
        ttk.Entry(pwd_frame, textvariable=self.pwd_url_var, state='readonly').pack(fill=tk.X, pady=5)
        
        pwd_info_frame = ttk.Frame(pwd_frame)
        pwd_info_frame.pack(fill=tk.X)
        self.pwd_var = tk.StringVar(value=self.password)
        ttk.Label(pwd_info_frame, text="访问密码：").pack(side=tk.LEFT)
        ttk.Entry(pwd_info_frame, textvariable=self.pwd_var, state='readonly', width=10).pack(side=tk.LEFT)
        ttk.Button(pwd_info_frame, text="复制密码", command=lambda: self.copy_text(self.pwd_var.get())).pack(side=tk.LEFT, padx=5)
        ttk.Button(pwd_info_frame, text="刷新密码", command=self.refresh_password).pack(side=tk.LEFT)

        # 二维码标签页
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # 直接访问二维码页
        direct_qr_frame = ttk.Frame(notebook)
        notebook.add(direct_qr_frame, text='直接访问二维码')
        self.direct_qr_label = ttk.Label(direct_qr_frame)
        self.direct_qr_label.pack(pady=10)

        # 密码访问二维码页
        pwd_qr_frame = ttk.Frame(notebook)
        notebook.add(pwd_qr_frame, text='密码访问二维码')
        self.pwd_qr_label = ttk.Label(pwd_qr_frame)
        self.pwd_qr_label.pack(pady=10)

        # 连接信息
        info_frame = ttk.LabelFrame(main_frame, text="连接信息", padding="5")
        info_frame.pack(fill=tk.X, pady=5)
        
        self.conn_var = tk.StringVar(value="当前连接数：0")
        ttk.Label(info_frame, textvariable=self.conn_var).pack()
        
        # 连接列表
        self.conn_list = ttk.Treeview(info_frame, columns=('ip', 'time'), show='headings', height=5)
        self.conn_list.heading('ip', text='IP地址')
        self.conn_list.heading('time', text='连接时间')
        self.conn_list.pack(fill=tk.X, pady=5)
        
        # 断开按钮
        ttk.Button(info_frame, text="断开选中连接", command=self.disconnect_selected).pack()

        # 状态栏
        self.status_var = tk.StringVar(value="服务器状态：准备就绪")
        ttk.Label(main_frame, textvariable=self.status_var).pack(pady=5)

        # 初始化URL和二维码
        self.update_urls()

    def on_device_select(self, event=None):
        """当选择音频设备时触发"""
        device_name = self.device_var.get()
        if device_name in self.audio_devices:
            self.selected_device = self.audio_devices[device_name]
            self.test_button['state'] = 'normal'
            self.start_button['state'] = 'normal'
            self.device_status_var.set(f"状态：已选择设备 - {device_name}")
            self.status_var.set("状态：设备已选择，可以开始测试或录制")
        else:
            self.selected_device = None
            self.test_button['state'] = 'disabled'
            self.start_button['state'] = 'disabled'
            self.device_status_var.set("状态：未选择设备")

    def test_device(self):
        """测试选中的音频设备"""
        if not self.selected_device:
            messagebox.showerror("错误", "请先选择音频设备")
            return

        def test_thread():
            try:
                # 禁用测试按钮
                self.test_button['state'] = 'disabled'
                self.device_status_var.set("状态：正在测试设备...")
                
                # 录制一小段音频
                with self.selected_device.recorder(samplerate=self.RATE, channels=self.CHANNELS) as mic:
                    data = mic.record(numframes=self.RATE)  # 录制1秒
                    data = (data * 32767).astype(np.int16)
                
                # 保存为临时WAV文件并播放
                import wave
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                    temp_path = temp_file.name
                
                with wave.open(temp_path, 'wb') as wf:
                    wf.setnchannels(self.CHANNELS)
                    wf.setsampwidth(2)  # 16-bit
                    wf.setframerate(self.RATE)
                    wf.writeframes(data.tobytes())
                
                # 播放测试音频
                winsound.PlaySound(temp_path, winsound.SND_FILENAME)
                
                # 删除临时文件
                os.unlink(temp_path)
                
                self.device_status_var.set("状态：设备测试完成")
                self.test_button['state'] = 'normal'
                
            except Exception as e:
                self.device_status_var.set(f"状态：设备测试失败 - {str(e)}")
                self.test_button['state'] = 'normal'
                messagebox.showerror("错误", f"测试设备时发生错误：{str(e)}")

        # 在新线程中运行测试
        threading.Thread(target=test_thread, daemon=True).start()

    def toggle_recording(self):
        """切换录制状态"""
        if not self.selected_device:
            messagebox.showerror("错误", "请先选择音频设备")
            return

        if not self.is_recording:
            # 启动录制
            self.is_recording = True
            self.start_button['text'] = "停止录制"
            self.device_status_var.set("状态：正在录制...")
            self.audio_thread = threading.Thread(target=self.capture_audio, daemon=True)
            self.audio_thread.start()
        else:
            # 停止录制
            self.is_recording = False
            self.start_button['text'] = "启动录制"
            self.device_status_var.set("状态：录制已停止")

    def capture_audio(self):
        """捕获音频"""
        try:
            with self.selected_device.recorder(samplerate=self.RATE, channels=self.CHANNELS, blocksize=self.CHUNK) as mic:
                while self.is_recording:
                    data = mic.record(numframes=self.CHUNK)
                    data = (data * 32767).astype(np.int16).tobytes()
                    if not self.audio_queue.full():
                        self.audio_queue.put(data)
        except Exception as e:
            self.is_recording = False
            self.root.after(0, lambda: self.device_status_var.set(f"状态：录制出错 - {str(e)}"))
            self.root.after(0, lambda: self.start_button.configure(text="启动录制"))
            self.root.after(0, lambda: messagebox.showerror("错误", f"录制时发生错误：{str(e)}"))

    # ... (保持其他方法不变，包括 generate_wav_header, generate_wav_stream 等)

    def run(self):
        """运行主程序"""
        # 启动Flask服务器线程
        server_thread = threading.Thread(target=self.run_flask, daemon=True)
        server_thread.start()

        # 运行GUI主循环
        self.root.mainloop()

if __name__ == "__main__":
    streamer = AudioStreamer()
    streamer.run()
