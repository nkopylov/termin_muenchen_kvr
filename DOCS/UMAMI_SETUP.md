# Umami Analytics Platform Setup Guide

**Last Updated:** 2025-10-14
**Umami Version:** Latest (PostgreSQL variant)

## Table of Contents

1. [Introduction](#introduction)
2. [What is Umami?](#what-is-umami)
3. [Prerequisites](#prerequisites)
4. [Deployment with Docker Compose](#deployment-with-docker-compose)
5. [Initial Configuration](#initial-configuration)
6. [Public Dashboard Setup](#public-dashboard-setup)
7. [Security & Best Practices](#security--best-practices)
8. [API Configuration](#api-configuration)
9. [Maintenance](#maintenance)
10. [Troubleshooting](#troubleshooting)

---

## Introduction

This guide provides complete instructions for deploying Umami, a lightweight, privacy-focused analytics platform. Umami is a self-hosted alternative to Google Analytics that respects user privacy and provides full data control.

### Key Features

- ✅ **Privacy-focused** - No cookies, GDPR compliant by design
- ✅ **Self-hosted** - Full control over your data
- ✅ **Public dashboards** - Share metrics without requiring authentication
- ✅ **Lightweight** - Minimal resource requirements (<512MB RAM)
- ✅ **Custom events** - Track any event with arbitrary properties
- ✅ **Real-time analytics** - Live activity monitoring
- ✅ **Simple API** - Easy integration via HTTP

---

## What is Umami?

Umami is an open-source, privacy-focused web analytics solution that can track:

- **Page views** (for websites)
- **Custom events** (for applications/bots)
- **User sessions**
- **Referrer sources**
- **Device/browser info** (for web)
- **Geographic data** (optional)

Unlike Google Analytics:
- No cookies required
- No tracking across sites
- No personal data collection
- Self-hosted (data never leaves your server)
- Open source (AGPLv3 license)

---

## Prerequisites

### Server Requirements

**Minimum Specifications:**
- **RAM:** 1GB
- **CPU:** 1 vCPU
- **Disk:** 25GB SSD
- **OS:** Linux (Ubuntu 22.04 recommended)

**Recommended Specifications:**
- **RAM:** 2GB
- **CPU:** 2 vCPU
- **Disk:** 50GB SSD

### Software Requirements

1. **Docker** (version 20.10+)
   ```bash
   # Install Docker (Ubuntu/Debian)
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   ```

2. **Docker Compose** (version 2.0+)
   ```bash
   # Usually included with Docker Desktop
   # Or install plugin:
   sudo apt-get update
   sudo apt-get install docker-compose-plugin
   ```

3. **Git** (for version control)
   ```bash
   sudo apt-get install git
   ```

### Optional (Recommended)

- **Domain name** - For accessing Umami via friendly URL
- **Reverse proxy** (nginx/Caddy) - For SSL/TLS
- **Firewall** (ufw) - For security

---

## Deployment with Docker Compose

### Step 1: Create Project Directory

```bash
# Create directory for Umami
mkdir -p ~/umami
cd ~/umami
```

### Step 2: Generate Secrets

Umami requires two secrets:

```bash
# Generate APP_SECRET (32 characters)
openssl rand -base64 32

# Generate DB_PASSWORD (32 characters)
openssl rand -base64 32
```

**Save these outputs!** You'll need them in the next step.

### Step 3: Create Environment File

Create `.env` file:

```bash
nano .env
```

Add the following content (replace with your generated secrets):

```env
# Umami Configuration
UMAMI_APP_SECRET=your-app-secret-from-step-2
UMAMI_DB_PASSWORD=your-db-password-from-step-2

# PostgreSQL Configuration
POSTGRES_DB=umami
POSTGRES_USER=umami
POSTGRES_PASSWORD=${UMAMI_DB_PASSWORD}

# Optional: Disable telemetry
DISABLE_TELEMETRY=1
```

### Step 4: Create Docker Compose File

Create `docker-compose.yml`:

```bash
nano docker-compose.yml
```

Add the following content:

```yaml
version: '3.8'

services:
  umami:
    image: ghcr.io/umami-software/umami:postgresql-latest
    container_name: umami
    environment:
      DATABASE_URL: postgresql://umami:${UMAMI_DB_PASSWORD}@umami-db:5432/umami
      DATABASE_TYPE: postgresql
      APP_SECRET: ${UMAMI_APP_SECRET}
      DISABLE_TELEMETRY: ${DISABLE_TELEMETRY:-0}
    ports:
      - "3000:3000"
    depends_on:
      umami-db:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - umami-network

  umami-db:
    image: postgres:15-alpine
    container_name: umami-db
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - umami-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - umami-network

volumes:
  umami-db-data:
    driver: local

networks:
  umami-network:
    driver: bridge
```

### Step 5: Deploy Umami

```bash
# Start containers
docker-compose up -d

# Verify containers are running
docker-compose ps

# Expected output:
# NAME        STATUS          PORTS
# umami       Up 30 seconds   0.0.0.0:3000->3000/tcp
# umami-db    Up 30 seconds   (healthy)
```

### Step 6: Check Logs

```bash
# View Umami logs
docker-compose logs -f umami

# You should see:
# ✓ Running at http://0.0.0.0:3000
# ✓ Database connection successful
```

### Step 7: Access Umami

Open your browser and navigate to:
```
http://your-server-ip:3000
```

Or if running locally:
```
http://localhost:3000
```

---

## Initial Configuration

### First Login

Umami comes with default credentials:

- **Username:** `admin`
- **Password:** `umami`

⚠️ **IMPORTANT:** Change these immediately after first login!

### Step 1: Change Admin Password

1. Click **Settings** (gear icon in top right)
2. Go to **Profile**
3. Click **Change Password**
4. Enter new secure password
5. Click **Save**

### Step 2: Create Your First Website

A "website" in Umami is a tracked entity (can be a website, app, or bot).

1. Click **Settings** → **Websites**
2. Click **Add Website**
3. Fill in the form:
   - **Name:** Your project name (e.g., "Munich Appointment Bot")
   - **Domain:** Leave blank for bots/apps, or add domain for websites
   - **Enable share URL:** Toggle ON (allows public dashboards)
4. Click **Save**

### Step 3: Get Your Website ID

After creating the website:

1. Click on the website name in the list
2. Look at the URL in your browser:
   ```
   http://localhost:3000/websites/abc123-def456-ghi789
                                      ^^^^^^^^^^^^^^^^^^^
                                      This is your Website ID
   ```
3. **Save this Website ID** - You'll need it for API integration

Alternative method:

1. Click **Settings** → **Websites**
2. Click **Edit** on your website
3. The **Website ID** is shown at the bottom of the form

---

## Public Dashboard Setup

Umami's public dashboard feature allows you to share analytics without requiring authentication.

### Step 1: Create a Dashboard

1. Click **Dashboards** in the left sidebar
2. Click **Create Dashboard**
3. Enter a name (e.g., "Public Statistics")
4. Click **Save**

### Step 2: Add Widgets to Dashboard

Umami supports various widget types:

#### A. Metrics Widget (Number Display)

1. Click **Add Widget**
2. Select **Metrics**
3. Configure:
   - **Website:** Select your website
   - **Type:** Choose metric type (Visitors, Page Views, Events, etc.)
   - **Date Range:** Last 24 hours, 7 days, 30 days, etc.
   - **Filter:** Optional event name or property filter
4. Click **Save**

#### B. Bar Chart Widget

1. Click **Add Widget**
2. Select **Bar**
3. Configure:
   - **Website:** Select your website
   - **Metric:** Events, Page Views, etc.
   - **Group By:** Event name, URL, referrer, etc.
   - **Date Range:** Time period
4. Click **Save**

#### C. Line Chart Widget

1. Click **Add Widget**
2. Select **Line**
3. Configure:
   - **Website:** Select your website
   - **Metric:** Events over time
   - **Date Range:** Time period
4. Click **Save**

### Step 3: Make Dashboard Public

1. Open your dashboard
2. Click the **three-dot menu** (⋮) in the top-right corner
3. Click **Dashboard Settings**
4. Toggle **Public** to ON
5. Click **Save**

### Step 4: Get Public URL

After making the dashboard public:

1. Click the **Share** button (or three-dot menu → Share)
2. Copy the **Public URL**
3. The URL format is:
   ```
   https://your-domain.com/share/DASHBOARD_ID/Dashboard-Name
   ```

This URL can be shared freely - no authentication required!

### Example: Public Dashboard for Bot

**Recommended widgets for a public bot dashboard:**

1. **Active Users (Last 30 Days)** - Metrics widget
   - Type: Unique visitors
   - Date range: Last 30 days

2. **Events Today** - Metrics widget
   - Type: Events
   - Date range: Last 24 hours

3. **Event Trend (Last 7 Days)** - Line chart
   - Metric: Events
   - Date range: Last 7 days

4. **Top Events** - Bar chart
   - Metric: Events
   - Group by: Event name
   - Date range: Last 7 days

5. **Activity by Hour** - Bar chart
   - Metric: Events
   - Group by: Hour
   - Date range: Last 24 hours

---

## Security & Best Practices

### 1. Change Default Credentials

Already covered in [Initial Configuration](#initial-configuration), but worth repeating:

⚠️ **Change the default admin password immediately!**

### 2. Configure Reverse Proxy with SSL

For production deployment, use a reverse proxy (nginx or Caddy) with SSL/TLS.

#### Option A: Nginx with Let's Encrypt

**Install nginx and certbot:**

```bash
sudo apt-get install nginx certbot python3-certbot-nginx
```

**Create nginx configuration:**

```bash
sudo nano /etc/nginx/sites-available/umami
```

Add:

```nginx
server {
    listen 80;
    server_name analytics.yourdomain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Enable site and get SSL certificate:**

```bash
sudo ln -s /etc/nginx/sites-available/umami /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Get SSL certificate
sudo certbot --nginx -d analytics.yourdomain.com
```

#### Option B: Caddy (Automatic SSL)

**Install Caddy:**

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

**Create Caddyfile:**

```bash
sudo nano /etc/caddy/Caddyfile
```

Add:

```caddy
analytics.yourdomain.com {
    reverse_proxy localhost:3000
}
```

**Reload Caddy:**

```bash
sudo systemctl reload caddy
```

Caddy automatically obtains and renews SSL certificates!

### 3. Configure Firewall

```bash
# Allow SSH (if you need remote access)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS (if using reverse proxy)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# If NOT using reverse proxy, allow Umami port directly
sudo ufw allow 3000/tcp

# Enable firewall
sudo ufw enable
```

### 4. Regular Backups

#### Backup PostgreSQL Database

Create a backup script:

```bash
nano ~/umami-backup.sh
```

Add:

```bash
#!/bin/bash
BACKUP_DIR="/home/$USER/umami-backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

docker exec umami-db pg_dump -U umami umami | gzip > $BACKUP_DIR/umami_$DATE.sql.gz

# Keep only last 7 days of backups
find $BACKUP_DIR -name "umami_*.sql.gz" -mtime +7 -delete

echo "Backup completed: umami_$DATE.sql.gz"
```

Make executable and schedule:

```bash
chmod +x ~/umami-backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add line:
0 2 * * * /home/yourusername/umami-backup.sh
```

#### Restore from Backup

```bash
# Stop Umami
cd ~/umami
docker-compose down

# Restore database
gunzip -c ~/umami-backups/umami_20251014_020000.sql.gz | \
  docker exec -i umami-db psql -U umami umami

# Restart Umami
docker-compose up -d
```

### 5. Data Retention Policy

Configure automatic data cleanup in Umami:

1. Go to **Settings** → **Websites**
2. Click **Edit** on your website
3. Scroll to **Data Retention**
4. Set retention period (e.g., 90 days, 1 year, etc.)
5. Click **Save**

This automatically deletes old data to manage disk usage.

---

## API Configuration

### API Endpoint

Umami provides a REST API for tracking events:

```
POST http://your-umami-domain.com/api/send
```

### Getting Your Website ID

See [Step 3 in Initial Configuration](#step-3-get-your-website-id).

### API Request Format

```bash
curl -X POST http://localhost:3000/api/send \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "website": "your-website-id-uuid",
      "url": "/event/user_registered",
      "name": "user_registered",
      "data": {
        "user_id": "12345",
        "source": "telegram"
      }
    }
  }'
```

### API Fields

- **website** (required): Your Website ID (UUID)
- **url** (optional): Virtual URL for the event (for page view tracking)
- **name** (required): Event name (e.g., "booking_completed")
- **data** (optional): Object with custom event properties

### Testing the API

```bash
# Test event tracking
curl -X POST http://localhost:3000/api/send \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "website": "abc123-def456-ghi789",
      "name": "test_event",
      "data": {
        "test": "true"
      }
    }
  }'

# Expected response (200 OK):
# (empty body is normal)
```

Then check your Umami dashboard - you should see the event!

### Rate Limiting

Umami does not have built-in rate limiting. For high-volume applications:

- Consider implementing client-side batching
- Use a reverse proxy with rate limiting (nginx `limit_req`)
- Monitor disk usage and scale accordingly

---

## Maintenance

### Updating Umami

```bash
cd ~/umami

# Pull latest image
docker-compose pull

# Restart with new image
docker-compose up -d

# Check logs
docker-compose logs -f umami
```

Umami automatically handles database migrations on startup.

### Monitoring Disk Usage

```bash
# Check PostgreSQL data size
docker exec umami-db du -sh /var/lib/postgresql/data

# Check Docker volumes
docker system df -v
```

### Database Maintenance

```bash
# Vacuum database (reclaim space)
docker exec umami-db psql -U umami -d umami -c "VACUUM FULL;"

# Analyze database (update statistics)
docker exec umami-db psql -U umami -d umami -c "ANALYZE;"
```

### Log Management

```bash
# View Umami logs
docker-compose logs umami

# View last 100 lines
docker-compose logs --tail=100 umami

# Follow logs in real-time
docker-compose logs -f umami

# View PostgreSQL logs
docker-compose logs umami-db
```

### Scaling Considerations

**When to scale:**
- PostgreSQL disk usage >80%
- RAM usage consistently >80%
- Slow query performance

**Scaling options:**
1. **Vertical scaling** - Upgrade VPS (more RAM/CPU)
2. **Storage expansion** - Add larger disk
3. **Database optimization** - Configure PostgreSQL tuning
4. **External PostgreSQL** - Use managed database (e.g., AWS RDS)

---

## Troubleshooting

### Issue: Umami container won't start

**Symptoms:**
```bash
docker-compose ps
# Shows: umami (Exit 1)
```

**Solution:**

```bash
# Check logs
docker-compose logs umami

# Common causes:
# 1. Wrong APP_SECRET format
# 2. Database connection issues
# 3. Port 3000 already in use

# Fix port conflict:
nano docker-compose.yml
# Change: "3001:3000" instead of "3000:3000"
docker-compose up -d
```

### Issue: Can't access Umami web interface

**Symptoms:**
- Browser shows "Connection refused"
- Can't access http://localhost:3000

**Solution:**

```bash
# 1. Check if container is running
docker-compose ps

# 2. Check firewall
sudo ufw status
sudo ufw allow 3000/tcp

# 3. Check if port is listening
sudo netstat -tlnp | grep 3000

# 4. Check container logs
docker-compose logs umami

# 5. Restart containers
docker-compose restart
```

### Issue: Database connection failed

**Symptoms:**
```
Error: Unable to connect to database
```

**Solution:**

```bash
# 1. Check PostgreSQL health
docker exec umami-db pg_isready -U umami

# 2. Verify environment variables
docker-compose config

# 3. Check DATABASE_URL format
# Should be: postgresql://umami:PASSWORD@umami-db:5432/umami

# 4. Restart database
docker-compose restart umami-db

# 5. Wait for healthy status
docker-compose ps
# Wait until umami-db shows (healthy)
```

### Issue: Public dashboard not accessible

**Symptoms:**
- Public URL requires login
- Dashboard link shows 404

**Solution:**

1. Verify dashboard is set to "Public":
   - Open dashboard
   - Click three-dot menu → Settings
   - Ensure **Public** toggle is ON
   - Save

2. Check the URL format:
   ```
   ✅ Correct: /share/DASHBOARD_ID/Dashboard-Name
   ❌ Wrong:   /dashboard/DASHBOARD_ID
   ```

3. Clear browser cache and try again

### Issue: Events not appearing in Umami

**Symptoms:**
- API returns 200 OK
- Events don't show in dashboard

**Solution:**

```bash
# 1. Verify Website ID is correct
# Check Settings → Websites → Your Website → Website ID

# 2. Test API manually
curl -X POST http://localhost:3000/api/send \
  -H "Content-Type: application/json" \
  -d '{
    "payload": {
      "website": "YOUR-WEBSITE-ID",
      "name": "test_event"
    }
  }'

# 3. Check if event appears in Real-time view
# Dashboard → Real-time (should show immediately)

# 4. Check database directly
docker exec umami-db psql -U umami -d umami -c \
  "SELECT COUNT(*) FROM website_event WHERE website_id = 'YOUR-WEBSITE-ID';"
```

### Issue: High disk usage

**Symptoms:**
- Disk space warning
- PostgreSQL volume growing rapidly

**Solution:**

```bash
# 1. Check database size
docker exec umami-db psql -U umami -d umami -c \
  "SELECT pg_size_pretty(pg_database_size('umami'));"

# 2. Configure data retention
# Settings → Websites → Edit → Data Retention → Set to 90 days

# 3. Manual cleanup (WARNING: deletes old data)
docker exec umami-db psql -U umami -d umami -c \
  "DELETE FROM website_event WHERE created_at < NOW() - INTERVAL '90 days';"

# 4. Vacuum database
docker exec umami-db psql -U umami -d umami -c "VACUUM FULL;"
```

### Issue: Slow query performance

**Symptoms:**
- Dashboard loads slowly
- API requests timing out

**Solution:**

```bash
# 1. Check database connection count
docker exec umami-db psql -U umami -d umami -c \
  "SELECT COUNT(*) FROM pg_stat_activity;"

# 2. Optimize database
docker exec umami-db psql -U umami -d umami -c "ANALYZE;"

# 3. Check for long-running queries
docker exec umami-db psql -U umami -d umami -c \
  "SELECT pid, now() - pg_stat_activity.query_start AS duration, query
   FROM pg_stat_activity
   WHERE state = 'active'
   ORDER BY duration DESC;"

# 4. Consider upgrading server resources
# Add more RAM, CPU, or use SSD storage
```

---

## Additional Resources

### Official Documentation
- Umami Documentation: https://umami.is/docs
- GitHub Repository: https://github.com/umami-software/umami

### Community
- Discord: https://discord.gg/4dz4zcXYrQ
- GitHub Discussions: https://github.com/umami-software/umami/discussions

### Useful Links
- API Documentation: https://umami.is/docs/api
- Cloud Hosting: https://cloud.umami.is (if you prefer managed hosting)
- Docker Hub: https://hub.docker.com/r/ghcr.io/umami-software/umami

---

## Conclusion

You now have a fully functional Umami analytics platform! Next steps:

1. ✅ Secure your installation with reverse proxy + SSL
2. ✅ Set up automated backups
3. ✅ Create your first public dashboard
4. ✅ Integrate with your application (see `ANALYTICS_INTEGRATION.md`)

For bot-specific integration instructions, refer to:
- **[ANALYTICS_INTEGRATION.md](./ANALYTICS_INTEGRATION.md)** - How to track events from your bot

---

**Questions or Issues?**

Check the [Troubleshooting](#troubleshooting) section or refer to the [Official Documentation](https://umami.is/docs).
