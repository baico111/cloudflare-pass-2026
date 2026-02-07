FROM python:3.10-slim

# 1. 设置系统环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 2. 安装系统依赖
RUN apt-get update -qq && apt-get install -y -qq \
    xvfb \
    xauth \
    python3-tk \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    wget \
    curl \
    unzip \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 3. 安装 Google Chrome
RUN wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y -qq /tmp/chrome.deb \
    && rm -f /tmp/chrome.deb

WORKDIR /app

# 4. 创建输出目录 (必须)
RUN mkdir -p /app/output && chmod 777 /app/output

COPY . .

# 5. 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pyvirtualdisplay seleniumbase loguru streamlit requests apscheduler

# 6. 预初始化 SeleniumBase (防止启动时下载慢)
RUN sbase install chromedriver

# 7. 启动命令 (核心修复点)
# a. 增加 rm -f /tmp/.X11-unix/X* 以清理残留的 X 锁文件，防止重启失败
# b. 建议在 app.py 和 scheduler.py 的 xvfb-run 命令中也加上 -a 参数
CMD ["sh", "-c", "rm -f /tmp/.X11-unix/X* && streamlit run app.py --server.port ${PORT:-8080} --server.address 0.0.0.0 & while true; do echo '--- 启动调度任务 ---'; python scheduler.py; sleep 3600; done"]
