--
-- PostgreSQL database dump
--

\restrict b9iB7wAWPSRMxhRGlq6XO76qZZUdGB3UHAJop25Ndkx6SjCVNOWvh1vg7d9LxK6

-- Dumped from database version 16.10 (Debian 16.10-1.pgdg12+1)
-- Dumped by pg_dump version 16.10 (Debian 16.10-1.pgdg12+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: postgres
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO postgres;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: postgres
--

COMMENT ON SCHEMA public IS '';


--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO postgres;

--
-- Name: audit_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.audit_logs (
    log_id integer NOT NULL,
    "timestamp" bigint NOT NULL,
    admin_user_id character varying(255) NOT NULL,
    action character varying(255) NOT NULL,
    details json,
    trace_id character varying(255)
);


ALTER TABLE public.audit_logs OWNER TO postgres;

--
-- Name: audit_logs_log_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.audit_logs_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.audit_logs_log_id_seq OWNER TO postgres;

--
-- Name: audit_logs_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.audit_logs_log_id_seq OWNED BY public.audit_logs.log_id;


--
-- Name: consolidated_reports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.consolidated_reports (
    id integer NOT NULL,
    review_id character varying(255) NOT NULL,
    round_num integer NOT NULL,
    report_data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.consolidated_reports OWNER TO postgres;

--
-- Name: consolidated_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.consolidated_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.consolidated_reports_id_seq OWNER TO postgres;

--
-- Name: consolidated_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.consolidated_reports_id_seq OWNED BY public.consolidated_reports.id;


--
-- Name: conversation_contexts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.conversation_contexts (
    context_id character varying(255) NOT NULL,
    room_id character varying(255) NOT NULL,
    user_id character varying(255) NOT NULL,
    summary text,
    key_topics text[],
    sentiment character varying(50),
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL
);


ALTER TABLE public.conversation_contexts OWNER TO postgres;

--
-- Name: kpi_snapshots; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.kpi_snapshots (
    snapshot_id integer NOT NULL,
    snapshot_date date NOT NULL,
    metric_name character varying(100) NOT NULL,
    value double precision NOT NULL,
    details json
);


ALTER TABLE public.kpi_snapshots OWNER TO postgres;

--
-- Name: kpi_snapshots_snapshot_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.kpi_snapshots_snapshot_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.kpi_snapshots_snapshot_id_seq OWNER TO postgres;

--
-- Name: kpi_snapshots_snapshot_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.kpi_snapshots_snapshot_id_seq OWNED BY public.kpi_snapshots.snapshot_id;


--
-- Name: memories; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.memories (
    memory_id character varying(255) NOT NULL,
    user_id character varying(255) NOT NULL,
    room_id character varying(255) NOT NULL,
    key text NOT NULL,
    value text NOT NULL,
    embedding public.vector(1536) NOT NULL,
    importance double precision DEFAULT 1.0,
    expires_at bigint,
    created_at bigint NOT NULL
);


ALTER TABLE public.memories OWNER TO postgres;

--
-- Name: messages; Type: TABLE; Schema: public; Owner: user
--

CREATE TABLE public.messages (
    message_id character varying(255) NOT NULL,
    room_id character varying(255) NOT NULL,
    user_id character varying(255) NOT NULL,
    role character varying(50) NOT NULL,
    "timestamp" bigint NOT NULL,
    embedding public.vector(1536),
    content bytea NOT NULL,
    content_searchable text NOT NULL,
    ts tsvector GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, COALESCE(content_searchable, ''::text))) STORED
);


ALTER TABLE public.messages OWNER TO "user";

--
-- Name: panel_reports; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.panel_reports (
    id integer NOT NULL,
    review_id character varying(255) NOT NULL,
    round_num integer NOT NULL,
    persona character varying(255) NOT NULL,
    report_data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.panel_reports OWNER TO postgres;

--
-- Name: panel_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.panel_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.panel_reports_id_seq OWNER TO postgres;

--
-- Name: panel_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.panel_reports_id_seq OWNED BY public.panel_reports.id;


--
-- Name: provider_configs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.provider_configs (
    provider_name character varying(100) NOT NULL,
    model character varying(100) NOT NULL,
    timeout_ms integer NOT NULL,
    retries integer NOT NULL,
    enabled boolean DEFAULT true NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.provider_configs OWNER TO postgres;

--
-- Name: review_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.review_events (
    event_id integer NOT NULL,
    review_id character varying(255) NOT NULL,
    ts bigint NOT NULL,
    type character varying(50) NOT NULL,
    round integer,
    actor character varying(255),
    content text
);


ALTER TABLE public.review_events OWNER TO postgres;

--
-- Name: review_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.review_events_event_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.review_events_event_id_seq OWNER TO postgres;

--
-- Name: review_events_event_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.review_events_event_id_seq OWNED BY public.review_events.event_id;


--
-- Name: review_metrics; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.review_metrics (
    review_id character varying(255) NOT NULL,
    total_duration_seconds double precision NOT NULL,
    total_tokens_used integer NOT NULL,
    total_cost_usd double precision NOT NULL,
    round_metrics jsonb,
    created_at bigint NOT NULL
);


ALTER TABLE public.review_metrics OWNER TO postgres;

--
-- Name: reviews; Type: TABLE; Schema: public; Owner: user
--

CREATE TABLE public.reviews (
    review_id character varying(255) NOT NULL,
    room_id character varying(255) NOT NULL,
    topic text NOT NULL,
    instruction text NOT NULL,
    status character varying(50) NOT NULL,
    total_rounds integer NOT NULL,
    current_round integer NOT NULL,
    created_at bigint NOT NULL,
    completed_at bigint,
    final_report jsonb
);


ALTER TABLE public.reviews OWNER TO "user";

--
-- Name: rooms; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.rooms (
    room_id character varying(255) NOT NULL,
    name character varying(255) NOT NULL,
    owner_id character varying(255) NOT NULL,
    type character varying(50) NOT NULL,
    parent_id character varying(255),
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL,
    message_count integer DEFAULT 0 NOT NULL
);


ALTER TABLE public.rooms OWNER TO postgres;

--
-- Name: summary_notes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.summary_notes (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    room_id text NOT NULL,
    week_start date NOT NULL,
    text text NOT NULL,
    tokens_saved_estimate integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.summary_notes OWNER TO postgres;

--
-- Name: system_settings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.system_settings (
    key character varying(100) NOT NULL,
    value_json jsonb NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.system_settings OWNER TO postgres;

--
-- Name: user_facts; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_facts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id text NOT NULL,
    kind text NOT NULL,
    key text NOT NULL,
    value_json jsonb NOT NULL,
    confidence double precision,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.user_facts OWNER TO postgres;

--
-- Name: user_profiles; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.user_profiles (
    user_id character varying(255) NOT NULL,
    role character varying(50) DEFAULT 'user'::character varying NOT NULL,
    name bytea,
    preferences bytea,
    conversation_style character varying(255) DEFAULT 'casual'::character varying,
    interests text[] DEFAULT '{}'::text[] NOT NULL,
    created_at bigint NOT NULL,
    updated_at bigint NOT NULL
);


ALTER TABLE public.user_profiles OWNER TO postgres;

--
-- Name: audit_logs log_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs ALTER COLUMN log_id SET DEFAULT nextval('public.audit_logs_log_id_seq'::regclass);


--
-- Name: consolidated_reports id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consolidated_reports ALTER COLUMN id SET DEFAULT nextval('public.consolidated_reports_id_seq'::regclass);


--
-- Name: kpi_snapshots snapshot_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kpi_snapshots ALTER COLUMN snapshot_id SET DEFAULT nextval('public.kpi_snapshots_snapshot_id_seq'::regclass);


--
-- Name: panel_reports id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.panel_reports ALTER COLUMN id SET DEFAULT nextval('public.panel_reports_id_seq'::regclass);


--
-- Name: review_events event_id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.review_events ALTER COLUMN event_id SET DEFAULT nextval('public.review_events_event_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: audit_logs audit_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.audit_logs
    ADD CONSTRAINT audit_logs_pkey PRIMARY KEY (log_id);


--
-- Name: consolidated_reports consolidated_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consolidated_reports
    ADD CONSTRAINT consolidated_reports_pkey PRIMARY KEY (id);


--
-- Name: consolidated_reports consolidated_reports_review_id_round_num_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consolidated_reports
    ADD CONSTRAINT consolidated_reports_review_id_round_num_key UNIQUE (review_id, round_num);


--
-- Name: conversation_contexts conversation_contexts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversation_contexts
    ADD CONSTRAINT conversation_contexts_pkey PRIMARY KEY (context_id);


--
-- Name: conversation_contexts conversation_contexts_room_id_user_id_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversation_contexts
    ADD CONSTRAINT conversation_contexts_room_id_user_id_key UNIQUE (room_id, user_id);


--
-- Name: kpi_snapshots kpi_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kpi_snapshots
    ADD CONSTRAINT kpi_snapshots_pkey PRIMARY KEY (snapshot_id);


--
-- Name: memories memories_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_pkey PRIMARY KEY (memory_id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (message_id);


--
-- Name: panel_reports panel_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.panel_reports
    ADD CONSTRAINT panel_reports_pkey PRIMARY KEY (id);


--
-- Name: panel_reports panel_reports_review_id_round_num_persona_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.panel_reports
    ADD CONSTRAINT panel_reports_review_id_round_num_persona_key UNIQUE (review_id, round_num, persona);


--
-- Name: provider_configs provider_configs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.provider_configs
    ADD CONSTRAINT provider_configs_pkey PRIMARY KEY (provider_name);


--
-- Name: review_events review_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.review_events
    ADD CONSTRAINT review_events_pkey PRIMARY KEY (event_id);


--
-- Name: review_metrics review_metrics_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.review_metrics
    ADD CONSTRAINT review_metrics_pkey PRIMARY KEY (review_id);


--
-- Name: reviews reviews_pkey; Type: CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_pkey PRIMARY KEY (review_id);


--
-- Name: rooms rooms_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_pkey PRIMARY KEY (room_id);


--
-- Name: summary_notes summary_notes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.summary_notes
    ADD CONSTRAINT summary_notes_pkey PRIMARY KEY (id);


--
-- Name: system_settings system_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.system_settings
    ADD CONSTRAINT system_settings_pkey PRIMARY KEY (key);


--
-- Name: kpi_snapshots uq_kpi_snapshot_date_metric; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.kpi_snapshots
    ADD CONSTRAINT uq_kpi_snapshot_date_metric UNIQUE (snapshot_date, metric_name);


--
-- Name: user_facts user_facts_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_facts
    ADD CONSTRAINT user_facts_pkey PRIMARY KEY (id);


--
-- Name: user_profiles user_profiles_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.user_profiles
    ADD CONSTRAINT user_profiles_pkey PRIMARY KEY (user_id);


--
-- Name: idx_memories_embedding; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_memories_embedding ON public.memories USING ivfflat (embedding) WITH (lists='100');


--
-- Name: idx_memories_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_memories_user_id ON public.memories USING btree (user_id);


--
-- Name: idx_messages_embedding; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_messages_embedding ON public.messages USING ivfflat (embedding) WITH (lists='100');


--
-- Name: idx_messages_room_id; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_messages_room_id ON public.messages USING btree (room_id);


--
-- Name: idx_messages_room_id_timestamp; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_messages_room_id_timestamp ON public.messages USING btree (room_id, "timestamp" DESC);


--
-- Name: idx_messages_ts; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_messages_ts ON public.messages USING gin (ts);


--
-- Name: idx_messages_user_id; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_messages_user_id ON public.messages USING btree (user_id);


--
-- Name: idx_review_events_review_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_review_events_review_id ON public.review_events USING btree (review_id);


--
-- Name: idx_review_events_review_id_ts; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_review_events_review_id_ts ON public.review_events USING btree (review_id, ts);


--
-- Name: idx_reviews_active; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_reviews_active ON public.reviews USING btree (room_id) WHERE ((status)::text = ANY ((ARRAY['pending'::character varying, 'in_progress'::character varying])::text[]));


--
-- Name: idx_reviews_room_created; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_reviews_room_created ON public.reviews USING btree (room_id, created_at);


--
-- Name: idx_reviews_room_id; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_reviews_room_id ON public.reviews USING btree (room_id);


--
-- Name: idx_reviews_status; Type: INDEX; Schema: public; Owner: user
--

CREATE INDEX idx_reviews_status ON public.reviews USING btree (status);


--
-- Name: idx_rooms_owner_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_rooms_owner_id ON public.rooms USING btree (owner_id);


--
-- Name: idx_rooms_parent_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_rooms_parent_id ON public.rooms USING btree (parent_id);


--
-- Name: idx_summary_notes_room_week; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_summary_notes_room_week ON public.summary_notes USING btree (room_id, week_start);


--
-- Name: idx_user_facts_user_kind_key; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX idx_user_facts_user_kind_key ON public.user_facts USING btree (user_id, kind, key);


--
-- Name: idx_user_profiles_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_user_profiles_user_id ON public.user_profiles USING btree (user_id);


--
-- Name: ix_audit_logs_admin_user_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_audit_logs_admin_user_id ON public.audit_logs USING btree (admin_user_id);


--
-- Name: ix_audit_logs_timestamp; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_audit_logs_timestamp ON public.audit_logs USING btree ("timestamp");


--
-- Name: ix_kpi_snapshots_date_metric; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_kpi_snapshots_date_metric ON public.kpi_snapshots USING btree (snapshot_date, metric_name);


--
-- Name: conversation_contexts conversation_contexts_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.conversation_contexts
    ADD CONSTRAINT conversation_contexts_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: panel_reports fk_review; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.panel_reports
    ADD CONSTRAINT fk_review FOREIGN KEY (review_id) REFERENCES public.reviews(review_id) ON DELETE CASCADE;


--
-- Name: consolidated_reports fk_review; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.consolidated_reports
    ADD CONSTRAINT fk_review FOREIGN KEY (review_id) REFERENCES public.reviews(review_id) ON DELETE CASCADE;


--
-- Name: memories memories_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.memories
    ADD CONSTRAINT memories_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: messages messages_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: review_events review_events_review_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.review_events
    ADD CONSTRAINT review_events_review_id_fkey FOREIGN KEY (review_id) REFERENCES public.reviews(review_id) ON DELETE CASCADE;


--
-- Name: review_metrics review_metrics_review_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.review_metrics
    ADD CONSTRAINT review_metrics_review_id_fkey FOREIGN KEY (review_id) REFERENCES public.reviews(review_id) ON DELETE CASCADE;


--
-- Name: reviews reviews_room_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: user
--

ALTER TABLE ONLY public.reviews
    ADD CONSTRAINT reviews_room_id_fkey FOREIGN KEY (room_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: rooms rooms_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.rooms
    ADD CONSTRAINT rooms_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.rooms(room_id) ON DELETE CASCADE;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: postgres
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO "user";


--
-- Name: TABLE alembic_version; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.alembic_version TO "user";


--
-- Name: TABLE audit_logs; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.audit_logs TO "user";


--
-- Name: SEQUENCE audit_logs_log_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.audit_logs_log_id_seq TO "user";


--
-- Name: TABLE consolidated_reports; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.consolidated_reports TO "user";


--
-- Name: SEQUENCE consolidated_reports_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.consolidated_reports_id_seq TO "user";


--
-- Name: TABLE conversation_contexts; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.conversation_contexts TO "user";


--
-- Name: TABLE kpi_snapshots; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.kpi_snapshots TO "user";


--
-- Name: SEQUENCE kpi_snapshots_snapshot_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.kpi_snapshots_snapshot_id_seq TO "user";


--
-- Name: TABLE memories; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.memories TO "user";


--
-- Name: TABLE panel_reports; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.panel_reports TO "user";


--
-- Name: SEQUENCE panel_reports_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.panel_reports_id_seq TO "user";


--
-- Name: TABLE provider_configs; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.provider_configs TO "user";


--
-- Name: TABLE review_events; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.review_events TO "user";


--
-- Name: SEQUENCE review_events_event_id_seq; Type: ACL; Schema: public; Owner: postgres
--

GRANT SELECT,USAGE ON SEQUENCE public.review_events_event_id_seq TO "user";


--
-- Name: TABLE review_metrics; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.review_metrics TO "user";


--
-- Name: TABLE rooms; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.rooms TO "user";


--
-- Name: TABLE summary_notes; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.summary_notes TO "user";


--
-- Name: TABLE system_settings; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.system_settings TO "user";


--
-- Name: TABLE user_facts; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.user_facts TO "user";


--
-- Name: TABLE user_profiles; Type: ACL; Schema: public; Owner: postgres
--

GRANT ALL ON TABLE public.user_profiles TO "user";


--
-- PostgreSQL database dump complete
--

\unrestrict b9iB7wAWPSRMxhRGlq6XO76qZZUdGB3UHAJop25Ndkx6SjCVNOWvh1vg7d9LxK6

