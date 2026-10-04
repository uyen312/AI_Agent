# ========================================================
# STAGE 1: Builder (Cài đặt thư viện C/Python và biên dịch wheels)
# ========================================================
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ========================================================
# STAGE 2: Runtime (Image thành phẩm siêu nhẹ & an toàn)
# ========================================================
FROM python:3.11-slim AS runner

WORKDIR /app

# Bắt buộc phải có tzdata để múi giờ Asia/Ho_Chi_Minh có hiệu lực
RUN apt-get update && apt-get install -y --no-install-recommends \
    tzdata \
    curl \
    && ln -snf /usr/share/zoneinfo/Asia/Ho_Chi_Minh /etc/localtime \
    && echo "Asia/Ho_Chi_Minh" > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Biến môi trường chuẩn Python Production
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Ho_Chi_Minh \
    PATH=/home/appuser/.local/bin:$PATH

# Tạo non-root user đảm bảo an toàn tuyệt đối
RUN groupadd -g 1001 appgroup && \
    useradd -u 1001 -g appgroup -m appuser

# Lấy các packages đã build từ Stage 1 sang (không mang rác compiler gcc)
COPY --from=builder --chown=appuser:appgroup /root/.local /home/appuser/.local

# Copy mã nguồn
COPY --chown=appuser:appgroup . .

# Tạo thư mục dữ liệu với đúng quyền cho appuser
RUN mkdir -p /app/data/logs /app/data/exports && \
    chown -R appuser:appgroup /app/data

USER appuser

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import sqlite3; conn = sqlite3.connect('data/events.db'); conn.execute('SELECT 1'); conn.close()" || exit 1

CMD ["python", "main.py"]