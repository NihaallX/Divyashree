-- Divyashree Neon setup (idempotent)
-- Consolidated final schema + WOW fields + Priya seed.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    name TEXT,
    phone TEXT,
    company TEXT,
    calendly_api_key TEXT,
    calendly_event_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    prompt_text TEXT,
    template_source TEXT,
    system_prompt TEXT,
    voice_settings JSONB DEFAULT '{}'::jsonb,
    llm_model VARCHAR(100) DEFAULT 'llama3:8b',
    temperature FLOAT DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE agents ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS prompt_text TEXT;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS template_source TEXT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'agents' AND column_name = 'system_prompt'
    ) THEN
        UPDATE agents
        SET prompt_text = COALESCE(prompt_text, system_prompt)
        WHERE prompt_text IS NULL OR prompt_text = '';
    END IF;
END $$;

UPDATE agents
SET prompt_text = 'You are a helpful AI assistant.'
WHERE prompt_text IS NULL OR prompt_text = '';

CREATE TABLE IF NOT EXISTS calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    campaign_id UUID,
    to_number VARCHAR(20) NOT NULL,
    from_number VARCHAR(20) NOT NULL,
    twilio_call_sid VARCHAR(255) UNIQUE,
    status VARCHAR(50) DEFAULT 'initiated',
    direction VARCHAR(20) DEFAULT 'outbound',
    duration INTEGER,
    recording_url TEXT,
    recording_duration INTEGER,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE calls ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS campaign_id UUID;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_url TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_duration INTEGER;

CREATE TABLE IF NOT EXISTS transcripts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID NOT NULL REFERENCES calls(id) ON DELETE CASCADE,
    speaker VARCHAR(20) NOT NULL,
    text TEXT NOT NULL,
    "timestamp" TIMESTAMPTZ DEFAULT NOW(),
    audio_duration FLOAT,
    confidence_score FLOAT,
    metadata JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS call_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID NOT NULL UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    summary TEXT,
    key_points TEXT[],
    user_sentiment VARCHAR(50),
    outcome VARCHAR(50),
    next_action VARCHAR(30),
    intent_category VARCHAR(20),
    budget_fit VARCHAR(10),
    geography_fit VARCHAR(10),
    timeline_fit VARCHAR(10),
    overall_grade VARCHAR(10),
    checkpoint_json JSONB,
    analyzed_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'::jsonb
);

ALTER TABLE call_analysis ADD COLUMN IF NOT EXISTS next_action VARCHAR(30);
ALTER TABLE call_analysis ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;
ALTER TABLE call_analysis ADD COLUMN IF NOT EXISTS intent_category VARCHAR(20);
ALTER TABLE call_analysis ADD COLUMN IF NOT EXISTS budget_fit VARCHAR(10);
ALTER TABLE call_analysis ADD COLUMN IF NOT EXISTS geography_fit VARCHAR(10);
ALTER TABLE call_analysis ADD COLUMN IF NOT EXISTS timeline_fit VARCHAR(10);
ALTER TABLE call_analysis ADD COLUMN IF NOT EXISTS overall_grade VARCHAR(10);
ALTER TABLE call_analysis ADD COLUMN IF NOT EXISTS checkpoint_json JSONB;

CREATE TABLE IF NOT EXISTS templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    description TEXT,
    category VARCHAR(50) DEFAULT 'custom',
    is_template BOOLEAN DEFAULT false,
    is_public BOOLEAN DEFAULT false,
    is_locked BOOLEAN DEFAULT false,
    owner_id VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID REFERENCES agents(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    source_file VARCHAR(255),
    source_url TEXT,
    file_type VARCHAR(50),
    metadata JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE CASCADE;
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS source_url TEXT;

CREATE TABLE IF NOT EXISTS auth_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    refresh_token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT,
    company TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, phone)
);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'campaign_state') THEN
        CREATE TYPE campaign_state AS ENUM ('draft', 'pending', 'running', 'paused', 'completed', 'failed');
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'contact_state') THEN
        CREATE TYPE contact_state AS ENUM ('pending', 'calling', 'completed', 'failed', 'skipped');
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS bulk_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agents(id),
    name TEXT NOT NULL,
    state campaign_state DEFAULT 'draft',
    timezone TEXT DEFAULT 'UTC',
    settings_snapshot JSONB NOT NULL DEFAULT '{"pacing":{"delay_seconds":10},"business_hours":{"enabled":false,"days":[1,2,3,4,5],"start_time":"09:00","end_time":"17:00"},"retry_policy":{"max_retries":3,"backoff_hours":[1,4,24],"retryable_outcomes":["no-answer","busy","failed"]}}'::jsonb,
    stats JSONB DEFAULT '{"total":0,"completed":0,"failed":0,"pending":0,"success_rate":0}'::jsonb,
    scheduled_start_time TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS campaign_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    campaign_id UUID NOT NULL REFERENCES bulk_campaigns(id) ON DELETE CASCADE,
    phone TEXT NOT NULL,
    name TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    call_id UUID REFERENCES calls(id),
    state contact_state DEFAULT 'pending',
    retry_count INT DEFAULT 0,
    outcome TEXT,
    locked_until TIMESTAMPTZ,
    last_attempted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'calls' AND constraint_name = 'calls_campaign_fk'
    ) THEN
        ALTER TABLE calls
            ADD CONSTRAINT calls_campaign_fk
            FOREIGN KEY (campaign_id) REFERENCES bulk_campaigns(id);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS scheduled_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    call_id UUID REFERENCES calls(id) ON DELETE CASCADE,
    campaign_id UUID,
    event_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    duration_minutes INTEGER DEFAULT 30,
    timezone VARCHAR(100) DEFAULT 'America/New_York',
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    cal_booking_id INTEGER,
    cal_booking_uid VARCHAR(255),
    cal_event_type_id INTEGER,
    status VARCHAR(50) DEFAULT 'scheduled',
    created_automatically BOOLEAN DEFAULT false,
    notes TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_calls_agent_id ON calls(agent_id);
CREATE INDEX IF NOT EXISTS idx_calls_user_id ON calls(user_id);
CREATE INDEX IF NOT EXISTS idx_calls_campaign ON calls(campaign_id) WHERE campaign_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calls_twilio_sid ON calls(twilio_call_sid);
CREATE INDEX IF NOT EXISTS idx_calls_status ON calls(status);
CREATE INDEX IF NOT EXISTS idx_calls_created_at ON calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_calls_recording_url ON calls(recording_url) WHERE recording_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_transcripts_call_id ON transcripts(call_id);
CREATE INDEX IF NOT EXISTS idx_transcripts_timestamp ON transcripts("timestamp");

CREATE INDEX IF NOT EXISTS idx_call_analysis_call_id ON call_analysis(call_id);
CREATE INDEX IF NOT EXISTS idx_call_analysis_grade ON call_analysis(overall_grade);
CREATE INDEX IF NOT EXISTS idx_call_analysis_intent ON call_analysis(intent_category);

CREATE INDEX IF NOT EXISTS idx_templates_category ON templates(category);
CREATE INDEX IF NOT EXISTS idx_templates_locked ON templates(is_locked);

CREATE INDEX IF NOT EXISTS idx_kb_agent_id ON knowledge_base(agent_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_user_id ON knowledge_base(user_id);
CREATE INDEX IF NOT EXISTS idx_kb_active ON knowledge_base(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_kb_source_url ON knowledge_base(source_url) WHERE source_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_kb_content_search ON knowledge_base USING gin(to_tsvector('english', content));

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_agents_user_id ON agents(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_id ON auth_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_refresh_token ON auth_tokens(refresh_token);

CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id);
CREATE INDEX IF NOT EXISTS idx_contacts_phone ON contacts(phone);

CREATE INDEX IF NOT EXISTS idx_campaigns_user_state ON bulk_campaigns(user_id, state);
CREATE INDEX IF NOT EXISTS idx_campaigns_user_created ON bulk_campaigns(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_campaigns_scheduled ON bulk_campaigns(scheduled_start_time) WHERE state = 'pending';
CREATE INDEX IF NOT EXISTS idx_contacts_campaign_state ON campaign_contacts(campaign_id, state);
CREATE INDEX IF NOT EXISTS idx_contacts_locked ON campaign_contacts(locked_until) WHERE locked_until IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_contacts_pending ON campaign_contacts(campaign_id, created_at) WHERE state = 'pending';

CREATE INDEX IF NOT EXISTS idx_scheduled_events_user_id ON scheduled_events(user_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_events_call_id ON scheduled_events(call_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_events_campaign_id ON scheduled_events(campaign_id);
CREATE INDEX IF NOT EXISTS idx_scheduled_events_scheduled_at ON scheduled_events(scheduled_at);
CREATE INDEX IF NOT EXISTS idx_scheduled_events_status ON scheduled_events(status);
CREATE INDEX IF NOT EXISTS idx_scheduled_events_cal_booking_id ON scheduled_events(cal_booking_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduled_events_cal_booking_uid
    ON scheduled_events(cal_booking_uid)
    WHERE cal_booking_uid IS NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'scheduled_events' AND constraint_name = 'check_event_source'
    ) THEN
        ALTER TABLE scheduled_events
            ADD CONSTRAINT check_event_source CHECK (call_id IS NOT NULL);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_agents_updated_at') THEN
        CREATE TRIGGER update_agents_updated_at
            BEFORE UPDATE ON agents
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_calls_updated_at') THEN
        CREATE TRIGGER update_calls_updated_at
            BEFORE UPDATE ON calls
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_contacts_updated_at') THEN
        CREATE TRIGGER update_contacts_updated_at
            BEFORE UPDATE ON contacts
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_campaigns_updated_at') THEN
        CREATE TRIGGER update_campaigns_updated_at
            BEFORE UPDATE ON bulk_campaigns
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_knowledge_base_updated_at') THEN
        CREATE TRIGGER update_knowledge_base_updated_at
            BEFORE UPDATE ON knowledge_base
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

INSERT INTO templates (name, content, description, category, is_template, is_public, is_locked)
SELECT
    'Professional Receptionist',
    'You are Emma, a professional AI receptionist. Keep responses short, polite, and helpful.',
    'Polite receptionist for answering calls and routing inquiries',
    'receptionist',
    true,
    true,
    true
WHERE NOT EXISTS (
    SELECT 1 FROM templates WHERE name = 'Professional Receptionist'
);

DO $$
DECLARE
    target_user_id UUID;
BEGIN
    -- Bootstrap local admin user if none exists (password must be rotated immediately).
    INSERT INTO users (id, email, password_hash, name)
    VALUES (
        'a0000000-0000-0000-0000-000000000001',
        'admin@divyashree.local',
        '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewrBBNEFfS9ZrR6e',
        'Divyashree Admin'
    )
    ON CONFLICT (id) DO NOTHING;

    SELECT id INTO target_user_id FROM users
    WHERE id = 'a0000000-0000-0000-0000-000000000001'
    LIMIT 1;

    IF target_user_id IS NULL THEN
        SELECT id INTO target_user_id FROM users ORDER BY created_at ASC LIMIT 1;
    END IF;

    IF target_user_id IS NOT NULL THEN
        INSERT INTO agents (
            id,
            user_id,
            name,
            prompt_text,
            template_source,
            llm_model,
            temperature,
            max_tokens,
            is_active
        )
        SELECT
            'c4083449-3d67-4696-9822-15770d9c0371',
            target_user_id,
            'Priya',
                        $PROMPT$
IDENTITY & PERSONA
You are Priya (Pree-yah), a senior property consultant at Div-yaa-shree Developers.
You are calling on behalf of the Whispers of the Wind (WOW) project - a luxury villa-plot
development in Nandi Valley, near Nun-dhee Hills, North Bengaluru.
Your tone is warm, aspirational, unhurried, and premium. You never sound salesy or pushy.
You are fluent in both English and Hindi. Match the caller language. If they switch, you switch.
Always use first names if the caller shares them.

PRONUNCIATION RULES (MANDATORY)
You MUST pronounce these words exactly as shown:
- Divyasree   => Div-yaa-shree
- Nandi       => Nun-dhee
- Devanahalli => Deh-vah-nah-hul-lee
- Lakh        => Laak
- Crore       => Krore
- Bengaluru   => Ben-gah-loo-roo
NEVER say "Divya-sree", "Nan-dee", or "Lakh" with H sound. These are hard errors.

CONVERSATION FLOW
PHASE 1 - INTRODUCTION (always first)
Say: "Hello, this is Priya calling from Div-yaa-shree Developers. I am reaching out about
our new luxury villa-plot project - Whispers of the Wind - in Nandi Valley near Nun-dhee Hills.
Do you have two minutes to speak?"
Wait for explicit permission. If NO => GRACEFUL EXIT. If YES => continue.

PHASE 2 - QUALIFICATION (4 checkpoints - SKIP any the caller already answered)

CHECKPOINT 1 - INTENT
Ask: "Are you looking for a weekend home for personal use, or is this more of an
investment opportunity for you?"
Capture: SELF_USE or INVESTMENT.

CHECKPOINT 2 - GEOGRAPHY
Ask: "How comfortable are you with the Nun-dhee Hills / Deh-vah-nah-hul-lee corridor
in North Bengaluru?"
If hesitant: "The area is just 45 minutes from Bengaluru city centre and 20 minutes from
Kempegowda International Airport. Connectivity has improved dramatically."
If still no: note it, proceed to graceful exit after pitch.

CHECKPOINT 3 - BUDGET
Ask: "Our plots start at 92.4 laak and go up to 2.46 krore, all-inclusive.
Does that broadly fit what you had in mind?"
If too high: "Would it be worth a quick call with our Property Expert?
They sometimes have flexible payment structures."

CHECKPOINT 4 - TIMELINE
Ask: "The project has possession expected in December 2029.
Does a phased timeline work for you?"
If concerned: "Many early investors see this as an advantage - locking in at pre-launch
pricing before the corridor fully appreciates."

PHASE 3 - THE PITCH
Say: "Let me paint a picture of what life at Whispers of the Wind looks like.
Imagine waking up in a valley where 74 percent of the land is open green space -
no concrete jungle, just nature. Your villa plot comes with access to a 20,000
square-foot clubhouse with a pool, gym, spa, and banquet spaces. There are eco-parks,
cycling trails, and the iconic Nun-dhee Hills right at your horizon. This is a gated
Private Valley community designed for people who value privacy, nature, and a certain
way of living. Plots range from 1,200 to 3,199 square feet."

PHASE 4 - CTA
Say: "I would love to connect you with one of our senior Property Experts who can walk
you through the exact plots available, the layout, and our current pricing.
Would [day] or [day] work for a 20-minute call?"
If they prefer a link: "I will send you a booking link via SMS right after this call."
Close: "Thank you so much for your time. We will be in touch. Have a wonderful day!"

EDGE CASES
IRRITATED CALLER: Say "I completely understand. I apologise for the interruption.
May I send you a one-page summary over WhatsApp instead?" If no: "Of course.
I will remove your number from our list. Have a great day." NEVER argue.

BUDGET FIT / LOCATION MISMATCH: "Nun-dhee Hills has seen 40 percent price appreciation
over the last 3 years - worth a conversation with our expert just to see the numbers."

CALLER VOLUNTEERS INFO EARLY: DO NOT re-ask that checkpoint. Acknowledge naturally.
Use affirmations: "Perfect", "That is great to know", "Understood", "Wonderful".

PROJECT DETAILS (answer if asked):
- RERA: PRM/KA/RERA/1251/446/PR/170924/006841
- Developer: Divyasree Developers (est. 1999, Bengaluru-based)
- Location: Sy.No. 22/3 and 22/4, Budigere Road, Devanahalli
- Plot sizes: 1200, 1500, 2400, 3199 sq.ft.
- Amenities: Infinity pool, clubhouse, gym, yoga lawn, eco-parks, children play area
- Payment: 10 percent on booking, milestone-based thereafter
- Total area: approx. 17 acres, 74 percent open space

LANGUAGE RULES
- Keep each turn under 40 words except during The Pitch.
- If caller speaks Hindi, respond fully in Hindi.
- Hindi intro: "Namaste, main Priya bol rahi hoon, Div-yaa-shree Developers se.
    Humara naya luxury project Whispers of the Wind, Nandi Valley mein,
    ke baare mein aapse baat karni thi. Kya aap do minute nikal sakte hain?"
- Max call duration: 3 minutes. Wrap up gracefully if approaching that.
- NEVER lie about pricing, timelines, or approvals.

POST-CALL EXTRACTION (output after every call as JSON):
{
    "intent_category": "SELF_USE | INVESTMENT | UNCLEAR",
    "budget_fit": "YES | MAYBE | NO",
    "geography_fit": "YES | HESITANT | NO",
    "timeline_fit": "YES | HESITANT | NO",
    "overall_grade": "HOT | WARM | COLD",
    "checkpoint_json": {
        "c1_intent": "PASS | SKIP | FAIL",
        "c2_geography": "PASS | SKIP | FAIL",
        "c3_budget": "PASS | SKIP | FAIL",
        "c4_timeline": "PASS | SKIP | FAIL"
    },
    "next_action": "BOOK_EXPERT_CALL | SEND_BROCHURE | DO_NOT_CONTACT",
    "summary": "1-2 sentence plain English summary"
}
GRADING: HOT = all checkpoints PASS. WARM = some HESITANT. COLD = any NO or not interested.
                        $PROMPT$,
            'WOW Consultant',
            'llama-3.3-70b-versatile',
            0.6,
            180,
            true
        WHERE NOT EXISTS (
            SELECT 1 FROM agents WHERE id = 'c4083449-3d67-4696-9822-15770d9c0371'
        );
    END IF;
END $$;
