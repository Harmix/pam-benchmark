
# PAM Memory Agent Guide

## Overview
This guide explains how to organize company information into a standardized folder structure optimized for AI agent navigation. It handles both **unstructured documents** (PDFs, docs) and **structured activity streams** (Linear, Slack).

## Folder Structure (Max 3 Levels Deep)

```
./
├── .processing/             # Processing tracking (at root level)
│   ├── manifest.json        # Master record of all processed files
│   ├── processing_log.md    # Human-readable processing history
│   └── archive/             # Original files after processing
│
├── company_name_context/    # Company folder with _context suffix
│   ├── README.md            # Company overview and navigation guide
│   ├── 01_company/          # Core company information
│   │   ├── profile.md       # Basic info, industry, size
│   │   └── ...
│   │
│   ├── 02_people/           # Human resources and contacts
│   │   ├── leadership/      # C-suite and board members
│   │   └── teams/           # Department structures
│   │
│   ├── 03_operations/       # How the company works
│   │   ├── processes/       # Standard operating procedures
│   │   └── tools_systems.md # Tech stack (Linear, Slack, etc.)
│   │
│   ├── 04_financials/       # Financial information
│   │   └── ...
│   │
│   ├── 05_documents/        # Static documents
│   │   ├── legal/
│   │   ├── templates/
│   │   └── communications/  # (Formal memos, not Slack chat)
│   │
│   ├── 06_projects/         # Project Management
│   │   ├── active/          # Current High-Level Projects/Epics
│   │   ├── backlog/         # Future/Todo items
│   │   └── archive/         # Completed items
│   │
│   ├── 07_strategy/         # Strategic planning
│   │   └── ...
│   │
│   ├── 08_relationships/    # External entities
│   │   └── ...
│   │
│   ├── 09_activity_streams/ # (NEW) Integration Data (Time-Series)
│   │   ├── daily_digests/   # The Narrative: "What happened today?"
│   │   │   └── [YYYY-MM-DD].md
│   │   ├── linear_objects/  # The Data: Specific Ticket History
│   │   │   └── [ticket_id].md
│   │   └── slack_threads/   # The Context: Extracted Conversations
│   │
│   └── artifacts/           # AI-generated outputs
│       ├── reports/
│       └── visualizations/
│
└── unsorted/                # Raw documents to be processed
```

## Processing Unstructured Information (PDFs, Docs, Emails)
*Refers to standard files placed in `unsorted/`.*

1. **Hashing**: Calculate hash of file content to check `manifest.json` for duplicates.
2. **Categorization**: Identify if it is a Contract (`05_documents/legal`), a Guide (`03_operations`), or a Report (`04_financials`).
3. **Extraction**: Create a Markdown file with metadata headers.
4. **Linking**: Convert names to `[[wikilinks]]`.

---

## Processing Structured Streams (Linear & Slack)

Data from integrations (like `event_history.json`) is processed differently. It is split into **Narratives** (Time) and **Objects** (Entities).

### The Stream Processing Workflow

#### Step 1: Ingest & Sort
When processing a JSON event stream:
1. **Sort** events chronologically by `timestamp`.
2. **Group** events by Date (YYYY-MM-DD).

#### Step 2: Create Daily Digests (`09_activity_streams/daily_digests/`)
Create or update a file named `YYYY-MM-DD_activity.md`. Convert JSON events into a narrative log.

**Input (JSON):**
```json
{
  "timestamp": "20241115T0900",
  "platform": "linear",
  "generation_meta_data": {
    "title": "Legacy system migration",
    "status": "todo",
    "lead": "alice"
  }
}
```

**Output (Markdown in Daily Digest):**
```markdown
### 09:00 - Engineering (Linear)
- **New Task**: [[Legacy system migration]] created.
- **Assignee**: [[Alice]]
- **Status**: Todo -> In Progress
```

#### Step 3: Update Entity State (Objects)
Events are not just history; they update the state of "Entities" in the system.

1.  **Linear Tickets**:
    *   Check if a file exists in `09_activity_streams/linear_objects/[ticket_title].md`.
    *   If not, create it using the Ticket Template.
    *   Update the "Status" and "Timeline" section of that file.

2.  **Major Projects**:
    *   If a Linear Ticket has `priority: urgent` or represents a large Epic, ensure it exists in `06_projects/active/`.

3.  **People**:
    *   Map `lead: "alice"` or `sender: "bob"` to `[[Alice Lastname]]` or `[[Bob Lastname]]`.
    *   Ensure these links point to valid files in `02_people/`.

### Naming Conventions for Streams
*   **Daily Digests**: `YYYY-MM-DD_activity.md`
*   **Linear Tickets**: `ticket_ID_descriptive_name.md` (e.g., `ENG-123_database_optimization.md`)
*   **Slack Threads**: `YYYY-MM-DD_topic_summary.md`

## Linking Strategy

The power of this system comes from linking the **Stream** to the **Context**.

1.  **Stream to Person**: "[[Alice]] commented on..." → Links to `02_people/leadership/alice.md`
2.  **Stream to Project**: "Working on [[Database Optimization]]..." → Links to `06_projects/active/database_opt.md`
3.  **Daily Digest to Ticket**: "Moved [[ENG-123]] to Done" → Links to `09_activity_streams/linear_objects/ENG-123.md`

## Maintenance Guidelines

### Daily
*   Ingest JSON streams from Linear/Slack.
*   Generate `09_activity_streams/daily_digests/[Today].md`.
*   Update status fields in `06_projects` based on ticket movements.

### Weekly
*   Review `unsorted/` for manual documents.
*   Check for "Orphaned Links" (People mentioned in streams who don't have profiles in `02_people`).
```

---

### 2. INTRO_TEMPLATE.md
*Changes: Updated "Technology" section to define Linear/Slack as Systems of Record.*

```markdown
---
title: Company Introduction Template
date: 2025-11-19
type: template
tags: [template, company-info, overview]
status: template
---

# [Company Name] - Company Overview

## Basic Information

### Identity
- **Legal Name**: [Full legal company name]
- **Trade Name/DBA**: [If different from legal name]
- **Founded**: [Year]
- **Incorporated**: [Date and jurisdiction]
- **Company Type**: [LLC, Corporation, Partnership, etc.]
- **Tax ID/EIN**: [If applicable]

### Location
- **Headquarters**: [Address]
- **Other Offices**: [List of locations]
- **Operating Regions**: [Geographic coverage]
- **Remote Work**: [Policy/percentage]

### Size & Scale
- **Employees**: [Number and breakdown]
  - Full-time: [#]
  - Part-time: [#]
  - Contractors: [#]
- **Annual Revenue**: [Amount or range]
- **Market Cap/Valuation**: [If applicable]
- **Growth Stage**: [Startup/Growth/Mature/Enterprise]

## Industry & Market

### Industry Classification
- **Primary Industry**: [Main sector]
- **Secondary Industries**: [Related sectors]
- **NAICS Code**: [If applicable]
- **SIC Code**: [If applicable]

### Market Position
- **Market Segment**: [B2B, B2C, B2G, etc.]
- **Target Customer**: [Primary customer profile]
- **Competitive Position**: [Leader/Challenger/Niche]
- **Market Share**: [Percentage if known]

### Business Model
- **Revenue Model**: [How the company makes money]
- **Pricing Strategy**: [Approach to pricing]
- **Sales Channels**: [Direct, indirect, online, etc.]
- **Key Partnerships**: [Strategic relationships]

## Products & Services

### Core Offerings
1. **[Product/Service 1]**
   - Description: [What it is]
   - Target Market: [Who buys it]
   - Revenue Contribution: [% of total]

2. **[Product/Service 2]**
   - Description: [What it is]
   - Target Market: [Who buys it]
   - Revenue Contribution: [% of total]

## Leadership & Governance

### Executive Team
- **CEO/President**: [[Name]] - [Brief background]
- **CFO**: [[Name]] - [Brief background]
- **COO**: [[Name]] - [Brief background]
- **Other C-Suite**: [List with links]

### Board of Directors
- **Chairman**: [[Name]]
- **Directors**: [List with links]

### Organizational Structure
- **Structure Type**: [Functional/Divisional/Matrix]
- **Key Departments**: [List main divisions]
- **Reporting Lines**: [Brief description]

## Technology & Infrastructure

### Systems of Record (Context Sources)
*These systems are the primary sources of truth for activity streams.*
- **Project Management**: Linear (Source for `06_projects` and `09_activity_streams`)
- **Communication**: Slack (Source for `09_activity_streams/daily_digests`)
- **Codebase**: [GitHub/GitLab]
- **Documentation**: [Notion/Confluence]

### Tech Stack
- **Core Systems**: [ERP, CRM, etc.]
- **Development**: [Languages, frameworks]
- **Infrastructure**: [Cloud, on-premise]
- **Security**: [Standards, certifications]

## Financial Snapshot

### Current Performance (Year/Quarter)
- **Revenue**: $[Amount]
- **Gross Margin**: [%]
- **EBITDA**: $[Amount]
- **Net Income**: $[Amount]

### Key Metrics
- **Customer Count**: [Number]
- **Average Deal Size**: $[Amount]
- **Growth Rate**: [YoY %]

## Strategy & Goals

### Mission Statement
> [Company mission]

### Vision Statement
> [Company vision]

### Strategic Priorities (Current Year)
1. [Priority 1]
2. [Priority 2]
3. [Priority 3]

## Culture & Values

### Core Values
1. **[Value 1]**: [Description]
2. **[Value 2]**: [Description]
3. **[Value 3]**: [Description]

## Stakeholders

### Investors/Owners
- **Ownership Structure**: [Private/Public/PE-backed]
- **Major Shareholders**: [List if applicable]

### Key Partners
- **Strategic Partners**: [[Partner names]]
- **Major Suppliers**: [[Supplier names]]

### Customer Base
- **Total Customers**: [Number]
- **Key Accounts**: [List major ones]

---

## Document Links

### Internal References
- Detailed Financials: [[04_financials/overview]]
- Organization Chart: [[02_people/teams/org_chart]]
- Strategic Plan: [[07_strategy/roadmap]]
- **Recent Activity**: [[09_activity_streams/daily_digests/]]

### External Sources
- Company Website: [URL]
- Annual Report: [Link if public]

---

*Template Version: 2.0 (Streams Enabled)*
*Instructions: Replace all [bracketed] placeholders with actual information.*
*Use [[double brackets]] to create links to other documents.*
```