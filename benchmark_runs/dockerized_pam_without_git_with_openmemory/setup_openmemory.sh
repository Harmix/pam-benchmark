#!/bin/bash
# setup_openmemory.sh

set -e

echo "=========================================="
echo "Setting up OpenMemory"
echo "=========================================="

# Clone OpenMemory if not exists
if [ ! -d "mem0" ]; then
    echo "Cloning mem0 repository..."
    git clone https://github.com/mem0ai/mem0.git
else
    echo "mem0 repository already exists"
fi

cd mem0/openmemory

# Create API .env file
echo "Creating API .env file..."
cat > api/.env <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY}
USER=pam_user_id
API_KEY=${OPENAI_API_KEY}
EOF

# Create UI .env file (optional, but keeps their setup happy)
echo "Creating UI .env file..."
cat > ui/.env <<EOF
NEXT_PUBLIC_API_URL=http://localhost:8765
NEXT_PUBLIC_USER_ID=pam_user_id
EOF

echo "OpenMemory setup complete!"
cd ../..