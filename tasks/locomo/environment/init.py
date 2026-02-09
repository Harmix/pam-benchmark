"""
Company Information Structure Generator
Generates standardized folder structure for organizing company information,
optimized for both static context and dynamic activity streams (Linear/Slack).
"""

import os
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime


def create_folder_structure(company_name="company"):
    """
    Creates the standardized folder structure for company information
    """
    # Sanitize company name for folder
    safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_'
                        for c in company_name.lower().replace(' ', '_'))

    # Add _context suffix to company folder
    base_path = Path(f"{safe_name}_context")

    # Define folder structure
    structure = {
        # Level 1 - Main folders
        "01_company": {
            "files": ["profile.md", "history.md", "mission_values.md", "products_services.md"]
        },
        "02_people": {
            "subfolders": {
                "leadership": {"files": []},
                "teams": {"files": []}
            }
        },
        "03_operations": {
            "subfolders": {
                "processes": {"files": []}
            },
            "files": ["tools_systems.md", "policies.md"]
        },
        "04_financials": {
            "subfolders": {
                "reports": {"files": []}
            },
            "files": ["overview.md", "projections.md"]
        },
        "05_documents": {
            "subfolders": {
                "legal": {"files": []},
                "templates": {"files": []},
                "communications": {"files": []}
            }
        },
        "06_projects": {
            "subfolders": {
                "active": {"files": []},  # For In-Progress Linear Epics/Projects
                "archive": {"files": []},  # For Completed items
                "backlog": {"files": []}  # (NEW) For high-priority Todo items
            }
        },
        "07_strategy": {
            "files": ["market_analysis.md", "swot.md", "goals_okrs.md", "roadmap.md"]
        },
        "08_relationships": {
            "subfolders": {
                "customers": {"files": []},
                "suppliers": {"files": []},
                "partners": {"files": []},
                "competitors": {"files": []},
                "regulators": {"files": []},
                "investors": {"files": []}
            }
        },
        # (NEW) SECTION FOR INTEGRATION DATA
        "09_activity_streams": {
            "subfolders": {
                "daily_digests": {"files": []},  # Chronological view (The "News Feed")
                "linear_objects": {"files": []},  # Specific Ticket History
                "slack_threads": {"files": []}  # Extracted important conversations
            }
        },
        "artifacts": {
            "subfolders": {
                "reports": {"files": []},
                "visualizations": {"files": []},
                "exports": {"files": []}
            }
        }
    }

    # Create base directory
    base_path.mkdir(exist_ok=True)
    print(f"✅ Created base directory: {base_path}")

    # Create README.md with navigation
    readme_content = generate_readme(company_name, safe_name)
    (base_path / "README.md").write_text(readme_content, encoding='utf-8')
    print(f"✅ Created README.md")

    # Create INTRO_TEMPLATE.md
    intro_content = generate_intro_template()
    (base_path / "INTRO_TEMPLATE.md").write_text(intro_content, encoding='utf-8')
    print(f"✅ Created INTRO_TEMPLATE.md")

    # Create folder structure
    for folder_name, content in structure.items():
        folder_path = base_path / folder_name
        folder_path.mkdir(exist_ok=True)
        print(f"📁 Created folder: {folder_name}/")

        # Create files in this folder
        if "files" in content and content["files"]:
            for file_name in content["files"]:
                file_path = folder_path / file_name
                if not file_path.exists():
                    file_content = generate_file_template(folder_name, file_name)
                    file_path.write_text(file_content, encoding='utf-8')
                    print(f"  📄 Created: {folder_name}/{file_name}")

        # Create subfolders
        if "subfolders" in content:
            for subfolder_name, subfolder_content in content["subfolders"].items():
                subfolder_path = folder_path / subfolder_name
                subfolder_path.mkdir(exist_ok=True)
                print(f"  📁 Created subfolder: {folder_name}/{subfolder_name}/")

                # Create files in subfolder
                if "files" in subfolder_content and subfolder_content["files"]:
                    for file_name in subfolder_content["files"]:
                        file_path = subfolder_path / file_name
                        if not file_path.exists():
                            file_content = generate_file_template(f"{folder_name}/{subfolder_name}", file_name)
                            file_path.write_text(file_content, encoding='utf-8')
                            print(f"    📄 Created: {folder_name}/{subfolder_name}/{file_name}")

    # Create .processing folder at root level
    processing_path = Path(".processing")
    processing_path.mkdir(exist_ok=True)

    # Create archive subfolder
    (processing_path / "archive").mkdir(exist_ok=True)

    # Create processing manifest
    manifest_path = processing_path / "manifest.json"
    if not manifest_path.exists():
        manifest_content = {
            "processed_files": {},
            "processing_sessions": [],
            "duplicate_groups": {}
        }
        manifest_path.write_text(json.dumps(manifest_content, indent=2), encoding='utf-8')

    # Create processing log
    log_path = processing_path / "processing_log.md"
    if not log_path.exists():
        log_content = f"# Processing Log\n\nCreated: {datetime.now().strftime('%Y-%m-%d')}\n"
        log_path.write_text(log_content, encoding='utf-8')

    # Create unsorted folder
    Path("unsorted").mkdir(exist_ok=True)

    print(f"\n✨ Successfully created structure for: {company_name}")
    print(f"📍 Location: ./{safe_name}_context/")
    return base_path


def generate_readme(company_name, folder_name):
    """Generate README.md content with navigation"""
    return f"""# {company_name} - Information Hub

**Folder:** `{folder_name}_context/`

## Quick Navigation

### 🏢 Static Context
- [[01_company/profile|Company Profile]]
- [[02_people/teams/|Teams & Org]]
- [[03_operations/tools_systems|Tools & Systems]]
- [[06_projects/active/|Active Projects]]

### 🌊 Activity Streams (Linear & Slack)
- [[09_activity_streams/daily_digests/|Daily Digests]] - *Chronological feed of work*
- [[09_activity_streams/linear_objects/|Linear Tickets]] - *Task definitions*
- [[09_activity_streams/slack_threads/|Key Discussions]] - *Extracted threads*

### 🧠 Artifacts
- [[artifacts/reports/|Generated Reports]]
- [[artifacts/visualizations/|Visualizations]]

---

## How to Use Activity Streams
1. **Daily Digests**: Look here to answer "What happened on [Date]?"
2. **Linear Objects**: Look here for specific ticket metadata and history.
3. **Linking**: Use tickets to link back to People ([[02_people]]) and higher-level Projects ([[06_projects]]).

*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*
"""


def generate_intro_template():
    """Generate INTRO_TEMPLATE.md content"""
    # (Kept minimal for brevity, structure remains similar to original)
    return f"""---
title: Company Introduction Template
date: {datetime.now().strftime('%Y-%m-%d')}
type: template
---
# Company Overview
[Insert Basic Info Here]
"""


def generate_file_template(folder_path, file_name):
    """Generate template content for each file based on its location"""

    templates = {
        "profile.md": """---
title: Company Profile
type: profile
tags: [company, overview]
---
# Company Profile
## Overview
[Description]
## Key Facts
- **Industry**: 
- **Headquarters**: 
""",

        # --- NEW TEMPLATE FOR ACTIVITY DIGESTS ---
        "daily_digest_template.md": """---
title: Daily Digest - YYYY-MM-DD
date: YYYY-MM-DD
type: digest
tags: [activity-stream, daily-log]
---

# Daily Activity Digest - {date}

## 📊 Summary
- **Focus**: [Main topic of the day]
- **Key Decisions**: [Decisions made]

## 🕘 Timeline
### Morning
- **09:00** (Linear): [[Ticket ID]] moved to In Progress by [[Person]]
- **09:30** (Slack): [[Person]] discussed [[Topic]] in #engineering

### Afternoon
- [Events...]

## 🔗 Context Links
- [[06_projects/active/project_name]]
""",
        # --- NEW TEMPLATE FOR SLACK CHANNELS ---
        "slack_channel_template.md": """---
    title: Channel - [channel_name]
    type: slack_channel
    source: slack
    tags: [slack, communication]
    ---

    # Channel: #[channel_name]

    ## Overview
    - **Purpose**: [What this channel is for]
    - **Members**: [Key participants]

    ## Messages

    ### [YYYY-MM-DD HH:MM] - @sender
    message content

    ### [YYYY-MM-DD HH:MM] - @sender
    message content

    ---

    ## Related Context
    - Projects: [[06_projects/active/related_project]]
    - People: [[02_people/teams/engineering]]
    """,

        # --- NEW TEMPLATE FOR LINEAR OBJECTS ---
        "linear_ticket_template.md": """---
title: [Linear ID] Ticket Title
type: ticket
source: linear
status: [todo/in_progress/done]
priority: [high/medium/low]
lead: [[Person Name]]
---

# [Ticket ID] Ticket Title

## Description
[Description from Linear]

## Timeline
- **Created**: YYYY-MM-DD
- **Started**: YYYY-MM-DD
- **Completed**: YYYY-MM-DD

## Related Context
- Project: [[06_projects/active/related_project]]
- Team: [[02_people/teams/engineering]]
""",

        # Standard placeholders for other files to prevent errors
        "history.md": "# Company History\n",
        "mission_values.md": "# Mission & Values\n",
        "products_services.md": "# Products & Services\n",
        "tools_systems.md": "# Tools & Systems\n",
        "policies.md": "# Policies\n",
        "overview.md": "# Financial Overview\n",
        "projections.md": "# Financial Projections\n",
        "market_analysis.md": "# Market Analysis\n",
        "swot.md": "# SWOT Analysis\n",
        "goals_okrs.md": "# Goals & OKRs\n",
        "roadmap.md": "# Strategic Roadmap\n",
    }

    # Get the base filename without folder path
    base_name = file_name.split('/')[-1]

    if base_name in templates:
        return templates[base_name]

    return f"""---
title: {file_name.replace('.md', '').replace('_', ' ').title()}
date: {datetime.now().strftime('%Y-%m-%d')}
type: document
---
# {file_name.replace('.md', '').replace('_', ' ').title()}
[Content]
"""


def main():
    parser = argparse.ArgumentParser(description='Generate folder structure')
    parser.add_argument('company_name', nargs='?', default='company')
    parser.add_argument('-c', '--company', dest='company_alt')

    args = parser.parse_args()
    company_name = args.company_alt if args.company_alt else args.company_name

    create_folder_structure(company_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
