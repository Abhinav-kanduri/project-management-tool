# ReleaseLens Chat: End-to-End Workflow

This document describes the currently implemented synchronous chat path in
`app/routes/chat.py`, from a user's query to the returned answer and persisted
conversation state.

> **Preview note:** Mermaid diagrams render in GitHub and Mermaid-enabled
> Markdown previews. If a viewer shows the fenced `mermaid` source literally,
> enable Mermaid support in that viewer or open this file in GitHub. The source
> remains readable as Markdown even when diagram rendering is unavailable.

## Request-to-response flow

```  mermaid
flowchart TD
    U([User enters a project question])
    C[Client creates a unique client_message_id<br/>and sends JSON with X-Actor]
    E{Which endpoint?}
    API[FastAPI validates the request body]

    U --> C --> E
    E -->|Convenience endpoint| P1[POST /api/v1/chat]
    E -->|Existing conversation| P2[POST /api/v1/chat/conversations/session_id/messages]
    P1 --> API
    P2 --> API

    API --> V{Request valid?}
    V -->|No| E422[Return validation error]
    V -->|Yes| SID{session_id supplied?}

    SID -->|No| CTX{product_space_id and<br/>project_id supplied?}
    CTX -->|No| ECTX[Return 422 INVALID_PROJECT_CONTEXT]
    CTX -->|Yes| PV[Verify the active Project belongs<br/>to the selected Product Space]
    PV -->|Invalid| ECTX
    PV -->|Valid| CS[Insert chat_sessions row<br/>status ACTIVE and actor X-Actor]
    CS --> LOCK

    SID -->|Yes| LOCK[Load and lock chat_sessions row<br/>by session_id and actor_id]
    LOCK --> FOUND{Session found for actor?}
    FOUND -->|No| E404[Return 404 CHAT_SESSION_NOT_FOUND]
    FOUND -->|Yes| ACTIVE{Session status ACTIVE?}
    ACTIVE -->|No| E409A[Return 409 CHAT_SESSION_ARCHIVED]
    ACTIVE -->|Yes| DUP[Look up USER message by<br/>session_id and client_message_id]

    DUP --> EXISTS{Duplicate exists?}
    EXISTS -->|No| CLASSIFY[Classify intent with read-only rules]
    EXISTS -->|Yes| SAME{Same message content?}
    SAME -->|No| E409D[Return 409 DUPLICATE_MESSAGE_CONFLICT]
    SAME -->|Yes| CACHE{Cached ASSISTANT response exists?}
    CACHE -->|Yes| CACHED[Return the original cached response]
    CACHE -->|No| CLASSIFY

    CLASSIFY --> ACTION{Mutation intent?<br/>create, update, edit, archive,<br/>delete, or reset}
    ACTION -->|Yes| READONLY[Create read-only refusal<br/>with no retrieval sources]
    ACTION -->|No| GROUND[Load Project grounding data]

    GROUND --> PROJECT{Project exists and active?}
    PROJECT -->|No| EP404[Return 404 PROJECT_NOT_FOUND]
    PROJECT -->|Yes| DATA[Query releases, features,<br/>user stories, and acceptance criteria]
    DATA --> RANK[Rank up to 5 feature/story sources<br/>using query-term matches]
    RANK --> PROMPT[Build guarded prompt containing<br/>the question and Project data]
    PROMPT --> OAI[OpenAI Responses API<br/>configured chat model]
    OAI --> MODEL{Model call succeeds?}
    MODEL -->|No| E502[Log server-side error and return<br/>502 CHAT_MODEL_FAILED]
    MODEL -->|Yes| ANSWER[Read response.output_text]

    READONLY --> SAVE
    ANSWER --> SAVE[Persist the completed turn in one transaction]

    SAVE --> M1[Insert USER chat_messages row]
    M1 --> INTENT[Insert chat_message_intents row]
    INTENT --> RETRIEVAL[Insert chat_retrieval_events row]
    RETRIEVAL --> RUN[Insert RUNNING chat_runs row]
    RUN --> M2[Insert ASSISTANT chat_messages row<br/>including cached response metadata]
    M2 --> DONE[Mark chat_runs COMPLETED]
    DONE --> SESSION[Update session intent, count, timestamps,<br/>and first-query title]
    SESSION --> COMMIT{Database commit succeeds?}
    COMMIT -->|No| ROLLBACK[Roll back transaction<br/>and return server error]
    COMMIT -->|Yes| JSON[Return JSON answer, intent, context,<br/>sources, search metadata, and IDs]
    JSON --> UI([Client renders the answer and citations])

    classDef failure fill:#ffe2e2,stroke:#b42318,color:#5c1010;
    classDef success fill:#dcfae6,stroke:#079455,color:#054f31;
    classDef external fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e;
    class E422,ECTX,E404,E409A,E409D,EP404,E502,ROLLBACK failure;
    class JSON,UI,CACHED success;
    class OAI external;
```

## Database end-to-end flow

This view shows both sides of database use: Project data is read to ground the
answer, and the completed chat turn is written to the five chat tables.

``` mermaid
flowchart LR
    USER(["User query"])
    CLIENT["Client<br/>message + client message ID + actor"]
    API["FastAPI<br/>chat route"]

    USER --> CLIENT
    CLIENT -->|"POST chat request"| API

    subgraph DB["Supabase PostgreSQL"]
        direction TB

        subgraph READ["Grounding reads"]
            PROJECTS[("projects")]
            RELEASES[("releases")]
            FEATURES[("features")]
            STORIES[("user_stories")]
            CRITERIA[("acceptance_criteria")]
        end

        subgraph WRITE["Conversation state and turn writes"]
            SESSIONS[("chat_sessions")]
            MESSAGES[("chat_messages")]
            INTENTS[("chat_message_intents")]
            RETRIEVALS[("chat_retrieval_events")]
            RUNS[("chat_runs")]
        end
    end

    API -->|"1. Create or lock actor-owned session"| SESSIONS
    API -->|"2. Check retry ID"| MESSAGES

    PROJECTS -->|"Project scope"| API
    RELEASES -->|"Release context"| API
    FEATURES -->|"Feature context and sources"| API
    STORIES -->|"Story context and sources"| API
    CRITERIA -->|"Acceptance criteria"| API

    API --> RANK["Rank up to five sources"]
    RANK --> PROMPT["Build guarded grounded prompt"]
    PROMPT --> AI["OpenAI Responses API"]
    AI -->|"Grounded answer"| API

    API -->|"3. Insert user message"| MESSAGES
    MESSAGES -->|"user message ID"| INTENTS
    MESSAGES -->|"user message ID"| RETRIEVALS
    MESSAGES -->|"user message ID"| RUNS
    API -->|"4. Insert assistant answer and cache"| MESSAGES
    API -->|"5. Complete run"| RUNS
    API -->|"6. Update counters, intent, title, timestamps"| SESSIONS

    SESSIONS -->|"7. Commit transaction"| RESPONSE["JSON response<br/>answer + intent + sources + IDs"]
    RESPONSE --> CLIENT
    CLIENT --> USER

    classDef database fill:#f3e8ff,stroke:#7e22ce,color:#3b0764;
    classDef external fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e;
    class PROJECTS,RELEASES,FEATURES,STORIES,CRITERIA,SESSIONS,MESSAGES,INTENTS,RETRIEVALS,RUNS database;
    class AI external;
```

## Runtime sequence

```
mermaid
sequenceDiagram
    autonumber
    actor U as User
    participant C as Client
    participant A as FastAPI Chat API
    participant D as Supabase PostgreSQL
    participant O as OpenAI API

    U->>C: Submit project-scoped question
    C->>A: POST query with retry ID, context, and actor
    A->>A: Validate request

    opt No session ID was supplied
        A->>D: Validate Product Space and Project
        D-->>A: Project and organization
        A->>D: Insert active chat session
        D-->>A: Session ID and thread ID
    end

    A->>D: Lock session for session ID and actor
    D-->>A: Session and resolved context
    A->>D: Check client message ID

    alt Completed duplicate request
        D-->>A: Cached response from assistant metadata
        A-->>C: Return the original response
    else New request
        A->>A: Classify intent

        alt Unsupported mutation request
            A->>A: Produce read-only refusal
        else Supported read request
            A->>D: Read Project, releases, features, stories, and criteria
            D-->>A: Structured Project grounding data
            A->>A: Rank sources and build guarded prompt
            A->>O: Generate grounded answer
            O-->>A: Answer text
        end

        A->>D: Insert user message, intent, retrieval event, and run
        A->>D: Insert assistant message and cached response
        A->>D: Complete run and update session
        A->>D: Commit transaction
        D-->>A: Persisted turn
        A-->>C: Return answer, intent, sources, metadata, and IDs
        C-->>U: Render grounded answer
    end
```

## Data written for each successful turn

| Order | Table | Data recorded |
|---:|---|---|
| 1 | `chat_messages` | User query, sequence number, and `client_message_id` |
| 2 | `chat_message_intents` | Intent, confidence, resolved context, and structured search plan |
| 3 | `chat_retrieval_events` | Original query, retrieval type, ranked sources, count, and latency |
| 4 | `chat_runs` | Per-turn run state, initially `RUNNING` |
| 5 | `chat_messages` | Assistant answer, model, latency, sources, and cached response payload |
| 6 | `chat_runs` | Final `COMPLETED` state, assistant message ID, and latency |
| 7 | `chat_sessions` | Current intent, confidence, message count, timestamps, and generated title |

## Important behavior and boundaries

- Chat is Project-scoped and read-only. Mutation requests return guidance to use
  the dashboard or Project Management API.
- `X-Actor` defaults to `local-user`; the session lookup uses both actor and
  session ID. Production authentication is not yet represented by this header.
- `client_message_id` makes completed retries idempotent: the original response
  is returned without another model call or another set of database inserts.
- Grounding is structured database retrieval, not vector search. It loads all
  active Project releases, features, user stories, and acceptance criteria, then
  ranks up to five feature/story citations with term matching.
- The model is instructed to answer only from supplied Project data, ignore
  instructions embedded in that data, avoid exposing internal identifiers, and
  acknowledge insufficient evidence.
- The model call occurs before the successful turn is persisted. A model failure
  returns `502 CHAT_MODEL_FAILED` and does not save the user or assistant message.
- The response is synchronous JSON. SSE streaming and LangGraph checkpoint
  orchestration are planned but are not part of the current execution path.

## Related conversation operations

```
mermaid
flowchart LR
    A[Conversation client] -->|Create| B[POST /conversations]
    A -->|List by Project and actor| C[GET /conversations]
    A -->|Load ordered history| D[GET /conversations/session_id/messages]
    A -->|Send another turn| E[POST /conversations/session_id/messages]
    A -->|Permanent delete| F[DELETE /conversations/session_id]

    B --> DB[(Chat persistence tables)]
    C --> DB
    D --> DB
    E --> DB
    F -->|Cascade delete| DB
```
