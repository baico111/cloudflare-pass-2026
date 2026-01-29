FROM python:3.10-slim

# 1. 设置系统环境变量
ENV DEBIAN_FRONTEND=noninteractive

# 2. 安装系统依赖 (补全了 xauth)
RUN apt-get update -qq && apt-get install -y -qq \
    xvfb \
    xauth \
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
COPY . .

# 4. 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install pyvirtualdisplay seleniumbase loguru streamlit

# 5. 启动命令 (运行可视化界面)
# 修改 CMD，让它同时启动 scheduler 和 streamlit
CMD python scheduler.py ; streamlit run app.py --server.port 8080 --server.address 0.0.0.0
