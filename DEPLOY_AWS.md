# AWS Deployment Guide — Agent Goldfinger

This guide covers deploying Agent Goldfinger on AWS using EC2 + RDS.

## Architecture Overview

```
                   ┌──────────────┐
                   │   Route 53   │
                   │   (DNS)      │
                   └──────┬───────┘
                          │
                   ┌──────▼───────┐
                   │     ALB      │
                   │  (HTTPS:443) │
                   └──────┬───────┘
                          │
              ┌───────────┴───────────┐
              │                       │
       ┌──────▼───────┐       ┌──────▼───────┐
       │   Nginx      │       │   Nginx      │
       │   :80/:443   │       │   (optional  │
       │              │       │    2nd EC2)  │
       ├──────────────┤       └──────────────┘
       │ Next.js :3000│
       │ Uvicorn :8000│
       └──────┬───────┘
              │
       ┌──────▼───────┐
       │   RDS        │
       │  PostgreSQL  │
       └──────────────┘
```

## 1. Prerequisites

- AWS account with IAM permissions for EC2, RDS, VPC, and Security Groups
- A domain name (optional, for SSL)
- SSH key pair created in your target AWS region

## 2. RDS (PostgreSQL)

### Create the instance

1. Go to **RDS → Create database**
2. Settings:
   - Engine: **PostgreSQL 14+**
   - Template: **Free tier** (or Production for real workloads)
   - DB instance identifier: `goldfinger-db`
   - Master username: `goldfinger`
   - Master password: choose a strong password
   - Instance class: `db.t3.micro` (free tier) or `db.t3.small`+
   - Storage: 20 GB gp3
   - **Public access: No** (keep in private subnet)
   - VPC: use your default VPC or create a dedicated one

3. Under **Additional configuration**:
   - Initial database name: `goldfinger`

4. Note the **endpoint** after creation (e.g., `goldfinger-db.xxxx.us-east-1.rds.amazonaws.com`)

### Security Group for RDS

- Allow inbound **TCP 5432** from the EC2 security group only

## 3. EC2 Instance

### Launch

1. Go to **EC2 → Launch instance**
2. Settings:
   - AMI: **Ubuntu 22.04 LTS** (or Amazon Linux 2023)
   - Instance type: `t3.small` minimum (2 vCPU, 2 GB RAM)
   - Key pair: select your SSH key
   - Storage: 20 GB gp3
   - Security group: allow **SSH (22)**, **HTTP (80)**, **HTTPS (443)**

### Connect

```bash
ssh -i your-key.pem ubuntu@<ec2-public-ip>
```

### Install system dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Python 3.9+
sudo apt install -y python3.9 python3.9-venv python3-pip

# Node.js 18 (via NodeSource)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Nginx
sudo apt install -y nginx

# PostgreSQL client (for running migrations)
sudo apt install -y postgresql-client

# PM2 (process manager for Node.js)
sudo npm install -g pm2
```

## 4. Deploy Backend

### Clone and configure

```bash
cd /opt
sudo mkdir goldfinger && sudo chown ubuntu:ubuntu goldfinger
cd goldfinger
git clone <your-repo-url> .

cd Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment variables

```bash
cat > /opt/goldfinger/Backend/.env << 'ENVEOF'
APP_NAME="Production Agent API"
ENVIRONMENT=production
DEBUG=false
API_VERSION=v1

HOST=127.0.0.1
PORT=8000

# Point to RDS
DATABASE_URL=postgresql+asyncpg://goldfinger:<rds-password>@<rds-endpoint>:5432/goldfinger

# Generate a new secret key for production
SECRET_KEY=<run: openssl rand -base64 32>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# NetSuite credentials
NETSUITE_ACCOUNT_ID=<account-id>
NETSUITE_CONSUMER_KEY=<key>
NETSUITE_CONSUMER_SECRET=<secret>
NETSUITE_TOKEN_ID=<token-id>
NETSUITE_TOKEN_SECRET=<token-secret>
NETSUITE_BASE_URL=https://<account-id>.suitetalk.api.netsuite.com/services/rest/query/v1/suiteql
NETSUITE_REALM=<account-id>

# CORS — use your domain
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
ENVEOF

chmod 600 /opt/goldfinger/Backend/.env
```

### Run database migrations

```bash
cd /opt/goldfinger/Backend
source .venv/bin/activate
alembic upgrade head
```

### Create systemd service

```bash
sudo tee /etc/systemd/system/goldfinger-api.service << 'EOF'
[Unit]
Description=Agent Goldfinger FastAPI Backend
After=network.target

[Service]
Type=simple
User=ubuntu
Group=ubuntu
WorkingDirectory=/opt/goldfinger/Backend
Environment="PATH=/opt/goldfinger/Backend/.venv/bin:/usr/local/bin:/usr/bin"
ExecStart=/opt/goldfinger/Backend/.venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 2 \
    --loop uvloop \
    --http httptools
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable goldfinger-api
sudo systemctl start goldfinger-api
sudo systemctl status goldfinger-api
```

## 5. Deploy Frontend

### Build

```bash
cd /opt/goldfinger/frontend
npm ci

# Configure API URL (use your domain or localhost if same-server)
echo 'NEXT_PUBLIC_API_BASE_URL=https://yourdomain.com/api/v1' > .env.local

npm run build
```

### Run with PM2

```bash
cd /opt/goldfinger/frontend
pm2 start npm --name "goldfinger-web" -- start
pm2 save
pm2 startup   # follow the printed command to enable on boot
```

## 6. Nginx Reverse Proxy

```bash
sudo tee /etc/nginx/sites-available/goldfinger << 'EOF'
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Frontend (Next.js)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }

    # Backend API
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/goldfinger /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

## 7. SSL/TLS with Let's Encrypt

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

Certbot will automatically update the Nginx config for HTTPS and set up auto-renewal.

Verify auto-renewal:

```bash
sudo certbot renew --dry-run
```

## 8. Security Hardening

### Security groups summary

| Service | Port | Source               |
| ------- | ---- | -------------------- |
| SSH     | 22   | Your IP only         |
| HTTP    | 80   | 0.0.0.0/0            |
| HTTPS   | 443  | 0.0.0.0/0            |
| Postgres| 5432 | EC2 security group   |

### Additional steps

```bash
# Disable password auth for SSH
sudo sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart sshd

# Enable UFW firewall
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable

# Set file permissions on .env
chmod 600 /opt/goldfinger/Backend/.env
```

## 9. Monitoring & Maintenance

### View logs

```bash
# Backend
sudo journalctl -u goldfinger-api -f

# Frontend
pm2 logs goldfinger-web

# Nginx
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Restart services

```bash
sudo systemctl restart goldfinger-api   # Backend
pm2 restart goldfinger-web              # Frontend
sudo systemctl restart nginx            # Nginx
```

### Deploy updates

```bash
cd /opt/goldfinger
git pull origin main

# Backend
cd Backend
source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
sudo systemctl restart goldfinger-api

# Frontend
cd ../frontend
npm ci
npm run build
pm2 restart goldfinger-web
```

## 10. Cost Estimate (Minimal Setup)

| Resource                  | Monthly Cost |
| ------------------------- | ------------ |
| EC2 t3.small              | ~$15         |
| RDS db.t3.micro (free tier) | $0 (1st year) |
| EBS 20 GB gp3             | ~$2          |
| Data transfer (moderate)  | ~$5          |
| **Total**                 | **~$22/mo**  |

After free tier: RDS db.t3.micro adds ~$13/mo.
