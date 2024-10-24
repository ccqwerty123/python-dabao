import tkinter as tk 
from tkinter import ttk, messagebox
import qrcode
from PIL import Image, ImageTk
import socket
import threading
import numpy as np
import queue
import random
import string
import jwt
from flask import Flask, Response, request
import time
from datetime import datetime, timedelta
import sounddevice as sd

class AudioStreamer:
    def __init__(self):
        self.app = Flask(__name__)
        self.audio_queue = queue.Queue(maxsize=50)
        self.connected_clients = {}  # {client_id: connection_time}
        self.password = self._generate_password()
        self.secret_key = self._generate_password(16)  
        self.max_clients = 1  
        self.virtual_device = None
        self.is_running = True
        
        self.quality_settings = {
            '低质量': {'samplerate': 22050, 'channels': 1},
            '中等质量': {'samplerate': 44100, 'channels': 2}, 
            '高质量': {'samplerate': 48000, 'channels': 2}
        }
        self.current_quality = '中等质量'

        self._setup_routes()
        self._setup_gui()

    def _generate_password(self, length=6):
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

    def _generate_token(self):
        expiration = datetime.now() + timedelta(hours=24)
        token = jwt.encode(
            {'password': self.password, 'exp': expiration},
            self.secret_key,
            algorithm='HS256'
        )
        return token

    def _get_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return 'localhost'

    def _setup_gui(self):
        self.root = tk.Tk()
        self.root.title("音频流服务器")
        self.root.geometry("500x850")
        
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self._create_quality_frame(main_frame)
        self._create_device_frame(main_frame)
        self._create_user_limit_frame(main_frame)
        self._create_access_frames(main_frame)
        self._create_qr_notebook(main_frame)
        self._create_connection_frame(main_frame)
        self._create_status_bar(main_frame)
        
        self._update_urls()

    def _create_quality_frame(self, parent):
        quality_frame = ttk.LabelFrame(parent, text="音频质量设置", padding="5")
        quality_frame.pack(fill=tk.X, pady=5)
        
        self.quality_var = tk.StringVar(value=self.current_quality)
        for quality in self.quality_settings.keys():
            ttk.Radiobutton(
                quality_frame,
                text=quality,
                variable=self.quality_var,
                value=quality,
                command=self._update_quality
            ).pack(side=tk.LEFT, padx=5)

    def _create_device_frame(self, parent):
        device_frame = ttk.LabelFrame(parent, text="虚拟设备控制", padding="5")
        device_frame.pack(fill=tk.X, pady=5)
        
        self.device_status_var = tk.StringVar(value="未创建")
        ttk.Label(device_frame, textvariable=self.device_status_var).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            device_frame,
            text="创建虚拟设备",
            command=self._create_virtual_device
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            device_frame,
            text="移除虚拟设备",
            command=self._remove_virtual_device
        ).pack(side=tk.LEFT, padx=5)

    def _create_user_limit_frame(self, parent):
        limit_frame = ttk.LabelFrame(parent, text="用户限制", padding="5")
        limit_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(limit_frame, text="最大连接数：").pack(side=tk.LEFT)
        self.max_clients_var = tk.StringVar(value="1")
        spinbox = ttk.Spinbox(
            limit_frame, 
            from_=1, 
            to=10, 
            width=5,
            textvariable=self.max_clients_var,
            command=lambda: setattr(self, 'max_clients', int(self.max_clients_var.get()))
        )
        spinbox.pack(side=tk.LEFT, padx=5)

    def _create_access_frames(self, parent):
        direct_frame = ttk.LabelFrame(parent, text="加密直接访问", padding="5")
        direct_frame.pack(fill=tk.X, pady=5)
        
        self.direct_url_var = tk.StringVar()
        ttk.Entry(direct_frame, textvariable=self.direct_url_var, state='readonly').pack(fill=tk.X, pady=5)
        ttk.Button(
            direct_frame, 
            text="复制链接", 
            command=lambda: self.root.clipboard_append(self.direct_url_var.get())
        ).pack()

        pwd_frame = ttk.LabelFrame(parent, text="密码访问", padding="5")
        pwd_frame.pack(fill=tk.X, pady=5)
        
        self.pwd_url_var = tk.StringVar()
        ttk.Entry(pwd_frame, textvariable=self.pwd_url_var, state='readonly').pack(fill=tk.X, pady=5)
        
        pwd_info_frame = ttk.Frame(pwd_frame)
        pwd_info_frame.pack(fill=tk.X)
        
        self.pwd_var = tk.StringVar(value=self.password)
        ttk.Label(pwd_info_frame, text="访问密码：").pack(side=tk.LEFT)
        ttk.Entry(pwd_info_frame, textvariable=self.pwd_var, state='readonly', width=10).pack(side=tk.LEFT)
        
        ttk.Button(
            pwd_info_frame, 
            text="复制密码", 
            command=lambda: self.root.clipboard_append(self.pwd_var.get())
        ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            pwd_info_frame, 
            text="更新密码", 
            command=self._update_password
        ).pack(side=tk.LEFT)

    def _create_qr_notebook(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        direct_qr_frame = ttk.Frame(notebook)
        notebook.add(direct_qr_frame, text='直接访问二维码')
        self.direct_qr_label = ttk.Label(direct_qr_frame)
        self.direct_qr_label.pack(pady=10)

        pwd_qr_frame = ttk.Frame(notebook)
        notebook.add(pwd_qr_frame, text='密码访问二维码')
        self.pwd_qr_label = ttk.Label(pwd_qr_frame)
        self.pwd_qr_label.pack(pady=10)

    def _create_connection_frame(self, parent):
        frame = ttk.LabelFrame(parent, text="连接信息", padding="5")
        frame.pack(fill=tk.X, pady=5)
        
        self.conn_var = tk.StringVar(value="当前连接数：0")
        ttk.Label(frame, textvariable=self.conn_var).pack()
        
        self.conn_list = ttk.Treeview(
            frame, 
            columns=('ip', 'time', 'quality'), 
            show='headings', 
            height=5
        )
        
        self.conn_list.heading('ip', text='IP地址')
        self.conn_list.heading('time', text='连接时间')
        self.conn_list.heading('quality', text='音频质量')
        
        self.conn_list.column('ip', width=150)
        self.conn_list.column('time', width=150)
        self.conn_list.column('quality', width=100)
        
        self.conn_list.pack(fill=tk.X, pady=5)

    def _create_status_bar(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)
        
        self.status_var = tk.StringVar(value="服务器状态：准备就绪")
        ttk.Label(frame, textvariable=self.status_var).pack(side=tk.LEFT)
        
        ttk.Button(
            frame,
            text="关闭服务器",
            command=self._shutdown
        ).pack(side=tk.RIGHT)

    def _update_quality(self):
        self.current_quality = self.quality_var.get()
        if self.virtual_device:
            self._remove_virtual_device()
            self._create_virtual_device()

    def _create_virtual_device(self):
        try:
            if self.virtual_device is None:
                devices = sd.query_devices()
                for i, device in enumerate(devices):
                    if 'CABLE' in device['name']:
                        self.virtual_device = {
                            'device_id': i,
                            'name': device['name'],
                            'quality': self.current_quality
                        }
                        self.device_status_var.set(f"已连接: {device['name']}")
                        return
                messagebox.showwarning("未找到虚拟设备", "请安装VB-CABLE或其他虚拟音频设备")
        except Exception as e:
            messagebox.showerror("创建虚拟设备失败", str(e))

    def _remove_virtual_device(self):
        if self.virtual_device:
            self.virtual_device = None
            self.device_status_var.set("未创建")

    def _update_password(self):
        if messagebox.askyesno("确认", "更新密码将断开所有当前连接，是否继续？"):
            self.password = self._generate_password()
            self.pwd_var.set(self.password)
            self.connected_clients.clear()
            self._update_urls()
            self._update_client_list()

    def _setup_routes(self):
        @self.app.route('/direct/<token>')
        def direct_access(token):
            try:
                data = jwt.decode(token, self.secret_key, algorithms=['HS256'])
                if data['password'] != self.password:
                    return '链接已过期', 403
                return self._serve_audio_page()
            except:
                return '无效的访问链接', 403

        @self.app.route('/login')
        def login_page():
            return '''
            <!DOCTYPE html>
            <html>
                <head>
                    <title>音频流服务器 - 登录</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                    <style>
                        body {
                            font-family: Arial;
                            background: #f5f5f5;
                            display: flex;
                            justify-content: center;
                            align-items: center;
                            min-height: 100vh;
                            padding: 20px;
                        }
                        .login-container {
                            background: white;
                            padding: 30px;
                            border-radius: 10px;
                            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                            width: 100%;
                            max-width: 400px;
                        }
                        h1 {
                            text-align: center;
                            color: #2196F3;
                            margin-bottom: 30px;
                        }
                        input {
                            width: 100%;
                            padding: 12px;
                            border: 1px solid #ddd;
                            border-radius: 5px;
                            margin-bottom: 20px;
                        }
                        button {
                            width: 100%;
                            padding: 12px;
                            background: #2196F3;
                            color: white;
                            border: none;
                            border-radius: 5px;
                            cursor: pointer;
                        }
                    </style>
                </head>
                <body>
                    <div class="login-container">
                        <h1>音频流服务器</h1>
                        <form action="/verify" method="post">
                            <input type="password" name="password" placeholder="请输入访问密码" required>
                            <button type="submit">登录</button>
                        </form>
                    </div>
                </body>
            </html>
            '''

        @self.app.route('/verify', methods=['POST'])
        def verify():
            if request.form.get('password') == self.password:
                return self._serve_audio_page()
            return '密码错误', 403

        @self.app.route('/audio')
        def audio():
            client_id = request.remote_addr
            if len(self.connected_clients) >= self.max_clients and client_id not in self.connected_clients:
                return '连接数已达到上限', 403

            self.connected_clients[client_id] = {
                'time': datetime.now(),
                'quality': self.current_quality
            }
            self._update_client_list()

            def generate():
                try:
                    while True:
                        if client_id not in self.connected_clients:
                            break
                        if not self.audio_queue.empty():
                            yield self.audio_queue.get()
                finally:
                    if client_id in self.connected_clients:
                        del self.connected_clients[client_id]
                        self._update_client_list()

            return Response(generate(), mimetype='audio/x-wav')

    def _serve_audio_page(self):
        return '''
        <!DOCTYPE html>
        <html>
            <head>
                <title>音频流播放器</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {
                        font-family: Arial;
                        background: #f5f5f5;
                        padding: 20px;
                    }
                    .container {
                        max-width: 600px;
                        margin: 0 auto;
                        background: white;
                        padding: 30px;
                        border-radius: 10px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }
                    h1 {
                        text-align: center;
                        color: #2196F3;
                        margin-bottom: 30px;
                    }
                    audio {
                        width: 100%;
                        margin: 20px 0;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>音频流播放器</h1>
                    <audio controls autoplay>
                        <source src="/audio" type="audio/wav">
                        您的浏览器不支持音频播放
                    </audio>
                </div>
            </body>
        </html>
        '''

    def _capture_audio(self):
        while self.is_running:
            try:
                if self.virtual_device:
                    quality = self.quality_settings[self.current_quality]
                    with sd.InputStream(
                        device=self.virtual_device['device_id'],
                        samplerate=quality['samplerate'],
                        channels=quality['channels'],
                        blocksize=1024,
                        dtype=np.float32
                    ) as stream:
                        while self.is_running and self.virtual_device:
                            data, _ = stream.read(1024)
                            data = (data * 32767).astype(np.int16).tobytes()
                            while self.audio_queue.qsize() >= 45:
                                try:
                                    self.audio_queue.get_nowait()
                                except queue.Empty:
                                    break
                            self.audio_queue.put(data)
            except Exception as e:
                messagebox.showerror("音频捕获错误", str(e))
            time.sleep(0.1)

    def _update_urls(self):
        base_url = f"http://{self._get_ip()}:5000"
        token = self._generate_token()
        
        direct_url = f"{base_url}/direct/{token}"
        self.direct_url_var.set(direct_url)
        
        pwd_url = f"{base_url}/login"
        self.pwd_url_var.set(pwd_url)
        
        # 更新二维码
        for url, label in [(direct_url, self.direct_qr_label), (pwd_url, self.pwd_qr_label)]:
            qr = qrcode.QRCode(version=1, box_size=10, border=4)
            qr.add_data(url)
            qr.make(fit=True)
            qr_image = qr.make_image(fill_color="black", back_color="white")
            qr_image = qr_image.resize((200, 200), Image.LANCZOS)
            photo = ImageTk.PhotoImage(qr_image)
            label.configure(image=photo)
            label.image = photo

    def _update_client_list(self):
        for item in self.conn_list.get_children():
            self.conn_list.delete(item)
        
        for client_ip, info in self.connected_clients.items():
            self.conn_list.insert('', 'end', values=(
                client_ip, 
                info['time'].strftime('%H:%M:%S'),
                info['quality']
            ))
        
        self.conn_var.set(f"当前连接数：{len(self.connected_clients)}/{self.max_clients}")

    def _shutdown(self):
        if messagebox.askyesno("确认", "确定要关闭服务器吗？"):
            self.is_running = False
            self._remove_virtual_device()
            self.connected_clients.clear()
            self.root.quit()

    def run(self):
        audio_thread = threading.Thread(target=self._capture_audio, daemon=True)
        audio_thread.start()

        server_thread = threading.Thread(
            target=lambda: self.app.run(host='0.0.0.0', port=5000, threaded=True),
            daemon=True
        )
        server_thread.start()

        self.root.mainloop()

if __name__ == "__main__":
    streamer = AudioStreamer()
    streamer.run()
