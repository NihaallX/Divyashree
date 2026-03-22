# Divyashree

AI-powered voice calling platform for outbound campaigns, lead qualification, appointment workflows, and call analytics.

This repository contains Divyashree architecture: frontend app, FastAPI backend, voice gateway, and PostgreSQL data layer.

## Overview

Divyashree helps teams automate high-volume voice communication with AI agents.

Implemented capabilities in this codebase include:
- AI agent configuration and prompt management
- Bulk campaign creation from contact files (CSV/Excel parsing)
- Outbound call triggering through Twilio
- Call transcripts, analysis, and campaign progress tracking
- Health, info, and operational log endpoints
- Authentication with signup/login/refresh flow

## Tech Stack

- Frontend: Next.js (App Router), TypeScript, Tailwind CSS
- Backend: FastAPI, Python, Supabase client with PostgreSQL (Neon-supported DB URL)
- Voice and AI: Twilio voice, Groq LLM, voice gateway service
- Infra: Docker Compose, Redis, ngrok/Cloudflare tunnel scripts

## Architecture

- Frontend (landing, auth, docs)
- Backend API (auth, agents, calls, campaigns, contacts, analytics, templates, knowledge base)
- Voice gateway (Twilio media/session handling)
- PostgreSQL data store

## Quick Start

### Prerequisites
- Node.js 18+
- Python 3.11+
- PostgreSQL-compatible database URL
- Twilio credentials
- Groq API key

### Option A: Local Docker
1. Configure `.env` at repo/backend level as required.
2. Start services:

```bash
docker-compose up --build -d
```

3. Verify backend:

```bash
curl http://localhost:8000/health
```

### Option B: Split Frontend + Backend Dev
1. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

2. Frontend

```bash
cd frontend
npm install
npm run dev
```

3. Open:
- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`

## Core API Surfaces

- System: `/health`, `/info`, `/api-credits`
- Auth: `/auth/signup`, `/auth/login`, `/auth/refresh`, `/auth/verify-token`
- Agents: `/agents`
- Calls: `/calls/outbound`, `/calls`, `/calls/{id}`
- Campaigns: `/campaigns`, `/campaigns/create`, `/campaigns/{id}/start`

Use [docs/Divyashree_API.postman_collection.json](docs/Divyashree_API.postman_collection.json) for endpoint testing.

## Common Use Cases

- Lead generation and pre-qualification before human handoff
- Appointment and follow-up call workflows
- Campaign-based outbound calling with contact uploads
- Voice-based status checks and customer outreach

## Service Ports

- Backend API: `http://localhost:8000`
- Voice Gateway: `http://localhost:8001`
- ngrok Inspector: `http://localhost:4040`

## Notes

- Branding and runtime naming are Divyashree.
- Some legacy docs/scripts are retained for migration reference.
