# Tool and Component Specifications

## B.4 Tool/Component Specifications

### B.4.1 Slack

1. **`get_unread_messages(limit: int = 50) → str`**  
   Retrieve unread messages grouped by channel/DM, automatically marked as read after retrieval

2. **`send_channel_message(channel: str, message: str) → str`**  
   Send message to a channel with @username mention support

3. **`send_direct_message(to_user: str, message: str) → str`**  
   Send direct message to another user

4. **`get_channel_messages(channel: str, limit: int = 50, after_id: str = None) → str`**  
   Retrieve channel messages with pagination support

5. **`get_direct_messages(with_user: str, limit: int = 50, after_id: str = None) → str`**  
   Retrieve DM conversation history with pagination

6. **`list_channels() → str`**  
   List all available channels in workspace

7. **`list_users() → str`**  
   List all users in the Slack workspace

8. **`send_offline_message(to_user: str, message: str) → str`**  
   Send offline message when away from desk

### B.4.2 Linear

1. **`create_ticket(title: str, description: str, team: str, ...) → str`** 
   Create new ticket with comprehensive metadata including priority, dates, labels, and milestones

2. **`update_ticket(ticket_id: str, ...) → str`** 
   Update existing ticket fields with authorization checks

3. **`get_ticket(ticket_id: str) → str`**  
   Retrieve comprehensive ticket details by ID

4. **`list_tickets(team: str = None, status: str = None, ...) → str`**  
   Query tickets with filtering by team, status, lead, milestone, priority, and date ranges

5. **`delete_ticket(ticket_id: str) → str`** 
   Permanently remove ticket (admin-only operation)

6. **`assign_ticket(ticket_id: str, lead: str) → str`** 
   Assign or reassign ticket ownership with notifications

7. **`add_team_member(team: str, member: str) → str`**  
   Add user to ML or Engineering team (admin-only)

8. **`remove_team_member(team: str, member: str) → str`**  
   Remove user from team (admin-only)

9. **`list_team_members(team: str = None) → str`**  
   List team membership for specified or all teams

10. **`create_milestone(name: str, description: str, start_date: str, end_date: str) → str`**  
    Create project milestone with unique naming (admin-only)

11. **`update_milestone_progress(milestone: str, completion_rate: float) → str`**  
    Update milestone completion and sync to associated tickets (admin-only)

12. **`list_milestones() → str`**  
    Retrieve all milestones with current progress status

### B.4.3 Git

1. **`list_remote_git_repositories() → str`**  
   List available remote repositories with clone instructions and commit information

### B.4.4 Shell Commands

The agent has access to its own filesystems into which it can execute shell commands such as `git clone` as well as `list_directory()`, `read_file()`, `search_file()`, etc.

## B.5 Memory Based Components

1. **`store_memory(content: str, metadata: dict = None) → str`**  
   Store important information in persistent memory for future recall and context building

2. **`search_memory(query: str, limit: int = 5) → str`**  
   Search for contextually relevant memories using hybrid semantic and keyword search

3. **`get_memories(limit: int = 10) → str`**  
   Retrieve recent stored memories for context awareness and debugging