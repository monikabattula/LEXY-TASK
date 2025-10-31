# Legal Document Assistant

A full-stack web application that helps fill in legal document templates through conversational AI.

## Features

- Upload .docx templates and automatically detect placeholders (names, dates, amounts, etc.)
- Conversational interface to fill placeholders with natural language
- AI-powered validation and suggestions
- Generate filled documents and download them
- HTML preview of completed documents

## Tech Stack

### Frontend
- React 18 + TypeScript
- Vite
- Tailwind CSS
- React Router
- React Query (TanStack Query)
- Axios

### Backend
- FastAPI (Python 3.11)
- SQLite (via SQLModel)
- Google Gemini API
- python-docx

### Storage
- Local disk storage for documents
- SQLite database for metadata

## Setup

### Prerequisites
- Node.js 20+ (upgraded from 18)
- Python 3.11+
- Google Gemini API Key

### Backend Setup

1. Navigate to backend directory:
```bash
cd backend
```

2. Create and activate virtual environment:
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows
# or
source .venv/bin/activate  # Linux/Mac
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set environment variables:
Create `.env` file in `backend/` directory:
```
APP_ENV=dev
DATA_DIR=./data
GEMINI_API_KEY=your_gemini_api_key_here
```

5. Run the backend:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at `http://localhost:8000`

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Set environment variables:
Create `.env` file in `frontend/` directory:
```
VITE_API_BASE=http://localhost:8000
```

4. Run the frontend:
```bash
npm run dev
```

Frontend will be available at `http://localhost:5173` (or the port Vite assigns)

## Usage

1. **Upload Document**: Go to the home page and upload a .docx template file
2. **Wait for Parsing**: The system will automatically detect placeholders using Gemini
3. **Fill Placeholders**: Chat with the AI assistant to provide values for each placeholder
4. **Render & Download**: Once all placeholders are filled, render and download the completed document

## API Endpoints

### Documents
- `POST /v1/documents/upload` - Upload a .docx file
- `GET /v1/documents/{document_id}` - Get document info
- `GET /v1/documents/{document_id}/placeholders` - List placeholders
- `POST /v1/documents/{document_id}/parse` - Manually trigger parsing
- `POST /v1/documents/{document_id}/render` - Render filled document
- `GET /v1/documents/{document_id}/download` - Download rendered document
- `GET /v1/documents/{document_id}/preview` - Get preview URL

### Sessions
- `POST /v1/sessions` - Create a new session
- `GET /v1/sessions/{session_id}` - Get session info
- `POST /v1/sessions/{session_id}/chat` - Send chat message

## Project Structure

```
lexy-task/
├── backend/
│   ├── app/
│   │   ├── api/v1/          # API routes
│   │   ├── core/            # Config, DB, LLM, storage
│   │   ├── models/          # SQLModel models
│   │   ├── services/        # Business logic
│   │   └── main.py          # FastAPI app
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── pages/           # React pages
│   │   ├── lib/             # API utilities
│   │   ├── App.tsx          # Router
│   │   └── main.tsx         # Entry point
│   └── package.json
└── README.md
```

## Development

- Backend auto-reloads on file changes (--reload flag)
- Frontend hot-reloads via Vite
- Database is created automatically on first run
- Documents stored in `backend/data/` directory

## Deployment Notes

For production deployment (e.g., Render):

1. **Backend**:
   - Add Persistent Disk for `/data` directory
   - Set environment variables in Render dashboard
   - Use production WSGI server (e.g., Gunicorn)

2. **Frontend**:
   - Build: `npm run build`
   - Serve static files from `dist/` directory
   - Update `VITE_API_BASE` to production backend URL

3. **CORS**: Update `allow_origins` in `backend/app/main.py` with actual frontend URL

## License

MIT
