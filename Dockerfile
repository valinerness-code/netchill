# Step 1: Use a lightweight Python base image
FROM python:3.11-slim

# Step 2: Set up the working directory inside the container
WORKDIR /app

# Step 3: Copy your project files into the container
COPY . .

# Step 4: Expose the web traffic port Render expects
EXPOSE 10000

# Step 5: Start the Python HTTP web server on port 10000
CMD ["python", "-m", "http.server", "10000"]
