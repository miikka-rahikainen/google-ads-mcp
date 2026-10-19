# Use a slim Python image
FROM python:3.11-slim

# Install uv from PyPI with a pinned version. The deployment host cannot pull
# images from ghcr.io, so the uv image is not used.
RUN pip install --no-cache-dir uv==0.12.6

# Set the working directory in the container
WORKDIR /app

# Copy the project files into the container
COPY . .

# Install the project and its dependencies
# We use --system to install into the system Python environment in the container
RUN uv pip install --system .

# Expose port 8080 (default for Cloud Run)
EXPOSE 8080

# Define the command to run the server
# This uses the entry point defined in pyproject.toml
CMD ["google-ads-mcp"]
