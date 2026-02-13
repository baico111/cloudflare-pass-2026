FROM python:3.10-slim

# 1. 设置系统环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
# 可以在此处设置默认授权码
ENV WEB_ACCESS_CODE=admin123

# 2. 安装系统依赖 (增加了备份字体支持，防止验证码截图乱码)
# 额外增加了 libnss3-tools 用于某些环境下的证书修复
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
    fonts-noto-cjk \
    wget \
    curl \
    unzip \
    libnss3-tools \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 3. 安装 Google Chrome
RUN wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get update \
    && apt-get install -y -qq /tmp/chrome.deb \
    && rm -f /tmp/chrome.deb

WORKDIR /app

# 4. 创建输出目录 (用于持久化配置、授权文件、策略文件及历史日志)
# ✨ 注入：确保历史日志目录在容器构建时即存在
RUN mkdir -p /app/output/history_logs && chmod -R 777 /app/output

COPY . .

# 5. 安装 Python 依赖
# 适配 HF：增加了 huggingface-hub 用于同步数据集
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir pyvirtualdisplay seleniumbase loguru streamlit requests apscheduler imaplib2 huggingface-hub

# 6. 预初始化 SeleniumBase (必须，用于过 CF)
RUN sbase install chromedriver

# 7. 启动命令 (适配两个代码的联动执行)
# ✨ 物理接电：启动时先清理 X 锁，随后并行启动面板与调度轮询
# 将 sleep 时间改为 1800s (30分钟)，以匹配 scheduler.py 中的 15分钟推送窗口，确保不会错过 09:00 推送
CMD ["sh", "-c", "rm -f /tmp/.X11-unix/X* && export MALLOC_ARENA_MAX=2 && export QT_X11_NO_MITSHM=1 && export _CHROME_STRATEGY=nosandbox && streamlit run app.py --server.port 7860 --server.address 0.0.0.0 & while true; do echo '--- [矩阵调度] 轮询开始 ---'; python scheduler.py; sleep 1800; done"]
