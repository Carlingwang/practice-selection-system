#!/bin/bash
set -e
cd /root/practice_selection

echo "=== Installing system deps ==="
apt-get update -qq && apt-get install -y -qq python3-pip python3-venv nginx > /dev/null 2>&1

echo "=== Setting up Python venv ==="
python3 -m venv venv
./venv/bin/pip install --upgrade pip -q
./venv/bin/pip install -r requirements.txt -q

echo "=== Creating systemd service ==="
cat > /etc/systemd/system/practice.service << 'EOF'
[Unit]
Description=Practice Selection System
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/practice_selection
Environment=DB_PATH=/root/practice_selection/practice.db
ExecStart=/root/practice_selection/venv/bin/gunicorn -w 4 -b 127.0.0.1:5000 app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

echo "=== Configuring Nginx ==="
cat > /etc/nginx/sites-available/practice << 'EOF'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/practice /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

echo "=== Starting services ==="
systemctl daemon-reload
systemctl enable practice
systemctl restart practice
nginx -t && systemctl restart nginx

echo ""
echo "==========================================="
echo "  ✅ 部署完成！"
echo "  学生入口: http://$(curl -s ifconfig.me)"
echo "  管理后台: http://$(curl -s ifconfig.me)/admin/login"
echo "  账号: admin / admin123"
echo "==========================================="
