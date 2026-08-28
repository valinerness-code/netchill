# Step 1: Use an official Python base image
FROM python:3.11-slim

# Step 2: Install Node.js and NPM cleanly
RUN apt-get update && apt-get install -y ca-certificates curl gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update && apt-get install nodejs -y \
    && rm -rf /var/lib/apt/lists/*

# Step 3: Set up the working directory (This replaces your 'cd' command)
WORKDIR /app

# Step 4: Copy and install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Step 5: Copy and install Node.js dependencies
COPY package*.json ./
RUN npm install

# Step 6: Copy the rest of your application code
COPY . .

# Step 7: Expose the port Render expects
EXPOSE 10000

# Step 8: Start the Python HTTP server on port 10000
CMD ["python", "-m", "http.server", "10000"]
