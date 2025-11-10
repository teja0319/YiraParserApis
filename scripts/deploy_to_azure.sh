#!/bin/bash

# Medical Report Parser - Azure VM Deployment Script
# This script deploys the microservice to Azure Spot VM

set -e  # Exit on error

echo "🔷 Medical Report Parser - Azure Deployment"
echo "============================================"
echo ""

# Check if running on Azure VM
if [ -f /etc/cloud/cloud.cfg.d/90_dpkg.cfg ]; then
    echo "✅ Detected Azure VM"
else
    echo "⚠️  Warning: This doesn't appear to be an Azure VM"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "Step 1: Installing system dependencies..."
echo "==========================================="

# Update system
sudo apt-get update
sudo apt-get upgrade -y

# Install Python 3.11
if ! command -v python3.11 &> /dev/null; then
    echo "Installing Python 3.11..."
    sudo apt-get install -y software-properties-common
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev python3-pip
else
    echo "✅ Python 3.11 already installed"
fi

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
else
    echo "✅ Docker already installed"
fi

# Install Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo apt-get install -y docker-compose
else
    echo "✅ Docker Compose already installed"
fi

# Install poppler-utils for PDF processing
echo "Installing poppler-utils..."
sudo apt-get install -y poppler-utils curl

echo ""
echo "Step 2: Setting up the application..."
echo "======================================"

# Create app directory
APP_DIR="/opt/medical-parser"
sudo mkdir -p $APP_DIR
sudo chown $USER:$USER $APP_DIR

# Copy application files (assumes running from project directory)
echo "Copying application files..."
cp -r . $APP_DIR/
cd $APP_DIR

# Create necessary directories
mkdir -p temp_uploads output pdfs

echo ""
echo "Step 3: Configuring environment..."
echo "==================================="

# Check for .env file
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << 'EOF'
# Gemini API Configuration
GEMINI_API_KEY=your_gemini_api_key_here

# Optional: API Keys for authentication
# API_KEYS=key1,key2,key3

# Database Configuration
DATABASE_PATH=./medical_reports.db

# Directory Configuration
PDF_DIRECTORY=./pdfs
OUTPUT_JSON_DIRECTORY=./output
EOF
    echo "⚠️  Please edit .env file and add your Gemini API key!"
    echo "   Run: nano $APP_DIR/.env"
else
    echo "✅ .env file already exists"
fi

echo ""
echo "Step 4: Creating systemd service..."
echo "===================================="

# Create systemd service file
sudo tee /etc/systemd/system/medical-parser-api.service > /dev/null << EOF
[Unit]
Description=Medical Report Parser API
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$APP_DIR
ExecStart=/usr/bin/docker-compose up -d
ExecStop=/usr/bin/docker-compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
sudo systemctl daemon-reload

echo ""
echo "Step 5: Configuring firewall..."
echo "================================"

# Check if ufw is installed
if command -v ufw &> /dev/null; then
    echo "Configuring UFW firewall..."
    sudo ufw allow 8000/tcp
    sudo ufw allow 80/tcp
    sudo ufw allow 443/tcp
    sudo ufw --force enable
else
    echo "⚠️  UFW not installed. Please configure firewall manually to allow port 8000"
fi

echo ""
echo "Step 6: Installing Nginx (reverse proxy)..."
echo "============================================"

if ! command -v nginx &> /dev/null; then
    sudo apt-get install -y nginx
fi

# Create Nginx configuration
VM_IP=$(curl -s ifconfig.me)
sudo tee /etc/nginx/sites-available/medical-parser > /dev/null << EOF
server {
    listen 80;
    server_name $VM_IP;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/medical-parser /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo ""
echo "============================================"
echo "✅ Deployment Complete!"
echo "============================================"
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Edit the .env file with your Gemini API key:"
echo "   sudo nano $APP_DIR/.env"
echo ""
echo "2. Start the microservice:"
echo "   sudo systemctl start medical-parser-api"
echo "   sudo systemctl enable medical-parser-api"
echo ""
echo "3. Check status:"
echo "   sudo systemctl status medical-parser-api"
echo "   docker-compose ps"
echo ""
echo "4. View logs:"
echo "   docker-compose logs -f"
echo ""
echo "5. Access the API:"
echo "   http://$VM_IP/"
echo "   http://$VM_IP/docs"
echo ""
echo "6. Test health check:"
echo "   curl http://$VM_IP/health"
echo ""
echo "============================================"
echo ""
echo "⚠️  IMPORTANT: Make sure to:"
echo "   - Add your Gemini API key to .env"
echo "   - Configure Azure NSG to allow port 80 and 8000"
echo "   - Start the service with: sudo systemctl start medical-parser-api"
echo ""
