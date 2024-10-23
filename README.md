这是一个 GitHub Actions 工作流配置文件，用于自动构建 Windows 可执行文件（EXE）。以下是详细说明：
触发条件

手动触发（workflow_dispatch）
当 py 目录下的 Python 文件发生变化时自动触发

主要功能

使用 PyInstaller 将 Python 脚本打包成 EXE 文件
生成两个版本的 EXE：

原始版本（未压缩）
使用 UPX 压缩后的版本


自动比较并显示压缩前后的文件大小
自动提交生成的 EXE 文件到仓库

目录结构
Copyrepository/
├── py/                    # Python 源代码目录
├── exe/
│   ├── original/         # 未压缩的 EXE 文件
│   └── compressed/       # UPX 压缩后的 EXE 文件
├── build/                # PyInstaller 构建临时文件
├── specs/                # PyInstaller spec 文件
└── .github/workflows/    # GitHub Actions 配置文件
工作流程

设置 Windows 环境并安装 Python 3.8
配置依赖缓存以加快构建速度
安装必要的 Python 包（PyInstaller、pywin32、pefile）
下载并设置 UPX 压缩工具
扫描 py 目录中的 Python 文件
为每个 Python 文件：

构建原始版本 EXE
构建压缩版本 EXE
计算并显示压缩比


将生成的 EXE 文件提交到仓库

这个工作流程适合需要定期将 Python 脚本打包成 Windows 可执行文件的项目，特别是当文件大小是一个考虑因素时。
