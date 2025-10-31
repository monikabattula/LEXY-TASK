# Deployment Guide

This guide covers deploying the Legal Document Assistant to production environments.

## Prerequisites

- Python 3.11+
- Node.js 20.11+ (20.19+ recommended for Vite 7, or stick with Vite 5)
- PostgreSQL or SQLite database
- Google Gemini API Key

## Backend Deployment

### Environment Variables

Create a `.env` file in the `backend/` directory with:

```bash
APP_ENV=production
DATA_DIR=/app/data
DATABASE_URL=postgresql://user:password@localhost/lexy_task  # or use SQLite for SQLite
GEMINI_API_KEY=your_gemini_api_key_here
```

**Important:** For production:
- Use PostgreSQL instead of SQLite for better concurrency
- Set `DATA_DIR` to an absolute path
- Use environment variables from your hosting provider (don't commit `.env` to git)

### Installation

```bash
cd backend
pip install --upgrade pip
pip install -r requirements.txt
```

### Running the Server

For production, use a production-ready WSGI server like Gunicorn with Uvicorn workers:

```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

Or with more configuration:

```bash
gunicorn app.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000 \
  --access-logfile - \
  --error-logfile - \
  --timeout 120 \
  --keep-alive 5
```

### Docker Deployment (Optional)

Create a `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory
RUN mkdir -p /app/data

# Expose port
EXPOSE 8000

# Run with gunicorn
CMD ["gunicorn", "app.main:app", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
```

Build and run:

```bash
docker build -t lexy-backend ./backend
docker run -p 8000:8000 --env-file backend/.env lexy-backend
```

## Frontend Deployment

### Environment Variables

The frontend needs to know where the backend API is located. Create a `.env.production` file in `frontend/`:

```bash
VITE_API_BASE=https://your-backend-domain.com
```

### Build

```bash
cd frontend
npm install
npm run build
```

This creates a `dist/` folder with optimized production files.

### Serving the Frontend

You can serve the built files with any static file server:

#### Nginx Example

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    root /app/frontend/dist;
    index index.html;
    
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### Docker Deployment (Optional)

Create a `frontend/Dockerfile`:

```dockerfile
FROM node:20-alpine as builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy source code
COPY . .

# Build the app
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built files
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

## Full Stack Deployment

### Option 1: Render.com

1. **Backend Service:**
   - Create a new Web Service
   - Connect your GitHub repository
   - Build Command: `cd backend && pip install -r requirements.txt`
   - Start Command: `gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`
   - Add environment variables in dashboard
   - Add Persistent Disk mount at `/app/data`

2. **Frontend Service:**
   - Create a new Static Site
   - Build Command: `cd frontend && npm install && npm run build`
   - Publish Directory: `frontend/dist`
   - Add environment variable: `VITE_API_BASE=https://your-backend.onrender.com`

### Option 2: Railway

1. **Backend:**
   - Create new project from GitHub
   - Select `backend/` as root directory
   - Add environment variables
   - Railway auto-detects Python and runs the app

2. **Frontend:**
   - Create new static site
   - Point to `frontend/dist` after build
   - Set environment variable for API URL

### Option 3: Self-Hosted with Docker Compose

Create `docker-compose.yml` in project root:

```yaml
version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - APP_ENV=production
      - DATA_DIR=/app/data
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/lexy_task
    volumes:
      - backend_data:/app/data
    depends_on:
      - db

  frontend:
    build: ./frontend
    ports:
      - "80:80"
    environment:
      - VITE_API_BASE=http://localhost:8000
    depends_on:
      - backend

  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_DB=lexy_task
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  backend_data:
  postgres_data:
```

Run:

```bash
docker-compose up -d
```

## Important Deployment Notes

### 1. CORS Configuration

The backend CORS is currently set to allow all origins (`allow_origins=["*"]`). For production, update `backend/app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-frontend-domain.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

### 2. File Storage

- Use persistent storage for `/data` directory
- Consider using cloud storage (S3, GCS, Azure Blob) for production
- Set up regular backups of the database and documents

### 3. Security

- Never commit `.env` files to version control
- Use strong database passwords
- Enable HTTPS/TLS
- Consider adding rate limiting
- Implement authentication if sharing resources

### 4. Database

For production, migrate from SQLite to PostgreSQL:

```bash
# Install psycopg2 for PostgreSQL
pip install psycopg2-binary

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

### 5. Monitoring

Add logging and monitoring:
- Set up application logging to files
- Use services like Sentry for error tracking
- Monitor API usage and performance

### 6. Scaling

For high traffic:
- Add a reverse proxy (Nginx, Traefik)
- Use multiple Gunicorn workers
- Consider horizontal scaling with load balancer
- Use a message queue for background tasks

## Troubleshooting

### Backend won't start
- Check environment variables are set correctly
- Verify database connection string
- Check port is available
- Review logs for error messages

### Frontend can't connect to backend
- Verify `VITE_API_BASE` is set correctly
- Check CORS settings
- Ensure backend is running and accessible
- Check firewall rules

### Gemini API errors
- Verify API key is valid and has quota
- Check network connectivity
- Review API usage limits

## Recent Fixes Applied

1. **Fixed `.env` file location**: Created `backend/.env` with proper Gemini API key
2. **Updated Vite version**: Downgraded to Vite 5.4.2 for Node.js 20.11.1 compatibility
3. **Created missing `lib/api.ts`**: Added API client utilities for frontend
4. **Updated requirements.txt**: Organized with all production dependencies

