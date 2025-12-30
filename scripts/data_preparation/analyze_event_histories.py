import os
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any

def load_event_histories(events_dir: str) -> List[Dict[str, Any]]:
    """Load all JSON files from the test_event_histories directory."""
    event_files = []
    events_path = Path(events_dir)

    if not events_path.exists():
        raise FileNotFoundError(f"Directory {events_dir} does not exist")

    for json_file in events_path.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                events_data = json.load(f)
                event_files.append({
                    'filename': json_file.name,
                    'events': events_data if isinstance(events_data, list) else [events_data]
                })
        except Exception as e:
            print(f"Warning: Could not load {json_file.name}: {e}")

    return event_files

def parse_timestamp(timestamp_str: str) -> datetime:
    """Parse timestamp in format YYYYMMDDTHHMM."""
    try:
        return datetime.strptime(timestamp_str, "%Y%m%dT%H%M")
    except:
        return None

def calculate_task_duration(events: List[Dict]) -> Dict[str, Any]:
    """Calculate duration for tasks from creation to completion."""
    task_timelines = defaultdict(list)

    for event in events:
        if event.get('platform') == 'linear':
            meta = event.get('generation_meta_data', {})
            title = meta.get('title')
            status = meta.get('status')
            timestamp = parse_timestamp(event.get('timestamp', ''))

            if title and timestamp:
                task_timelines[title].append({
                    'timestamp': timestamp,
                    'status': status
                })

    durations = []
    for title, timeline in task_timelines.items():
        timeline.sort(key=lambda x: x['timestamp'])
        start_time = timeline[0]['timestamp']

        done_events = [t for t in timeline if t['status'] == 'done']
        if done_events:
            end_time = done_events[0]['timestamp']
            duration_days = (end_time - start_time).total_seconds() / (24 * 3600)
            durations.append({
                'task': title,
                'duration_days': round(duration_days, 2),
                'start': start_time.strftime('%Y-%m-%d'),
                'end': end_time.strftime('%Y-%m-%d')
            })

    return durations

def extract_quantitative_metrics(event_files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract comprehensive quantitative metrics from event histories."""
    metrics = {
        'total_files': len(event_files),
        'total_events': 0,
        'platforms': defaultdict(int),
        'generation_types': defaultdict(int),
        'teams': defaultdict(int),
        'priorities': defaultdict(int),
        'statuses': defaultdict(int),
        'leads': defaultdict(int),
        'slack_senders': defaultdict(int),
        'slack_channels': defaultdict(int),
        'task_titles': defaultdict(int),
        'status_transitions': defaultdict(int),
        'tasks_by_team': defaultdict(int),
        'tasks_by_priority': defaultdict(int),
        'completed_tasks': 0,
        'cancelled_tasks': 0,
        'in_progress_tasks': 0,
        'todo_tasks': 0,
        'tasks_with_lead_changes': defaultdict(int),
        'tasks_with_deadline_extensions': defaultdict(int),
        'slack_messages_per_channel': defaultdict(int),
        'slack_messages_per_sender': defaultdict(int),
        'events_by_date': defaultdict(int),
        'events_by_hour': defaultdict(int),
        'unique_task_titles': set(),
        'unique_leads': set(),
        'unique_slack_senders': set(),
        'completed_task_durations': [],
        'all_task_durations': []
    }

    for file_data in event_files:
        events = file_data['events']
        metrics['total_events'] += len(events)

        task_durations = calculate_task_duration(events)
        metrics['all_task_durations'].extend(task_durations)

        task_leads = defaultdict(set)
        task_deadlines = defaultdict(list)

        for event in events:
            platform = event.get('platform', 'unknown')
            generation_type = event.get('generation_type', 'unknown')
            timestamp = event.get('timestamp', '')

            metrics['platforms'][platform] += 1
            metrics['generation_types'][generation_type] += 1

            if timestamp:
                ts = parse_timestamp(timestamp)
                if ts:
                    date_str = ts.strftime('%Y-%m-%d')
                    hour = ts.hour
                    metrics['events_by_date'][date_str] += 1
                    metrics['events_by_hour'][hour] += 1

            meta = event.get('generation_meta_data', {})

            if platform == 'linear':
                team = meta.get('team')
                priority = meta.get('priority')
                status = meta.get('status')
                lead = meta.get('lead')
                title = meta.get('title')
                expected_finish = meta.get('expected_finish_date')

                if team:
                    metrics['teams'][team] += 1
                    if status:
                        metrics['tasks_by_team'][f"{team}:{status}"] += 1

                if priority:
                    metrics['priorities'][priority] += 1
                    if status:
                        metrics['tasks_by_priority'][f"{priority}:{status}"] += 1

                if status:
                    metrics['statuses'][status] += 1
                    if status == 'done':
                        metrics['completed_tasks'] += 1
                    elif status == 'cancelled':
                        metrics['cancelled_tasks'] += 1
                    elif status == 'in_progress':
                        metrics['in_progress_tasks'] += 1
                    elif status == 'todo':
                        metrics['todo_tasks'] += 1

                if lead:
                    metrics['leads'][lead] += 1
                    metrics['unique_leads'].add(lead)
                    if title:
                        task_leads[title].add(lead)

                if title:
                    metrics['task_titles'][title] += 1
                    metrics['unique_task_titles'].add(title)

                    if expected_finish:
                        task_deadlines[title].append(expected_finish)

            elif platform == 'slack':
                sender = meta.get('sender')
                channel = meta.get('channel')

                if sender:
                    metrics['slack_senders'][sender] += 1
                    metrics['slack_messages_per_sender'][sender] += 1
                    metrics['unique_slack_senders'].add(sender)

                if channel:
                    metrics['slack_channels'][channel] += 1
                    metrics['slack_messages_per_channel'][channel] += 1

        for title, leads in task_leads.items():
            if len(leads) > 1:
                metrics['tasks_with_lead_changes'][title] = len(leads)

        for title, deadlines in task_deadlines.items():
            unique_deadlines = set(deadlines)
            if len(unique_deadlines) > 1:
                metrics['tasks_with_deadline_extensions'][title] = len(unique_deadlines)

    metrics['platforms'] = dict(metrics['platforms'])
    metrics['generation_types'] = dict(metrics['generation_types'])
    metrics['teams'] = dict(metrics['teams'])
    metrics['priorities'] = dict(metrics['priorities'])
    metrics['statuses'] = dict(metrics['statuses'])
    metrics['leads'] = dict(metrics['leads'])
    metrics['slack_senders'] = dict(metrics['slack_senders'])
    metrics['slack_channels'] = dict(metrics['slack_channels'])
    metrics['task_titles'] = dict(metrics['task_titles'])
    metrics['tasks_by_team'] = dict(metrics['tasks_by_team'])
    metrics['tasks_by_priority'] = dict(metrics['tasks_by_priority'])
    metrics['slack_messages_per_channel'] = dict(metrics['slack_messages_per_channel'])
    metrics['slack_messages_per_sender'] = dict(metrics['slack_messages_per_sender'])
    metrics['events_by_date'] = dict(sorted(metrics['events_by_date'].items()))
    metrics['events_by_hour'] = dict(sorted(metrics['events_by_hour'].items()))
    metrics['tasks_with_lead_changes'] = dict(metrics['tasks_with_lead_changes'])
    metrics['tasks_with_deadline_extensions'] = dict(metrics['tasks_with_deadline_extensions'])

    metrics['unique_task_count'] = len(metrics['unique_task_titles'])
    metrics['unique_leads_count'] = len(metrics['unique_leads'])
    metrics['unique_slack_senders_count'] = len(metrics['unique_slack_senders'])

    del metrics['unique_task_titles']
    del metrics['unique_leads']
    del metrics['unique_slack_senders']

    if metrics['all_task_durations']:
        durations = [d['duration_days'] for d in metrics['all_task_durations']]
        metrics['avg_task_duration_days'] = round(sum(durations) / len(durations), 2)
        metrics['min_task_duration_days'] = round(min(durations), 2)
        metrics['max_task_duration_days'] = round(max(durations), 2)

    if metrics['total_events'] > 0:
        metrics['avg_events_per_file'] = round(metrics['total_events'] / metrics['total_files'], 2)

    return metrics

def save_detailed_extracts(event_files: List[Dict[str, Any]]):
    """Save detailed extracts for further analysis."""
    all_events = []

    for file_data in event_files:
        for event in file_data['events']:
            event_extract = {
                'source_file': file_data['filename'],
                'timestamp': event.get('timestamp'),
                'platform': event.get('platform'),
                'generation_type': event.get('generation_type'),
                'metadata': event.get('generation_meta_data', {})
            }
            all_events.append(event_extract)

    all_events.sort(key=lambda x: x.get('timestamp', ''))

    with open('all_events_chronological.json', 'w', encoding='utf-8') as f:
        json.dump(all_events, f, indent=2, ensure_ascii=False)

def main():
    events_dir = './test_event_histories'

    print("Loading event histories from test_event_histories directory...")
    event_files = load_event_histories(events_dir)
    print(f"Found {len(event_files)} event history files\n")

    if len(event_files) == 0:
        print("No JSON files found in test_event_histories directory!")
        return

    print("Extracting quantitative metrics...")
    metrics = extract_quantitative_metrics(event_files)

    with open('event_metrics.json', 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    save_detailed_extracts(event_files)

    print("\n" + "="*70)
    print("EXTRACTION COMPLETE")
    print("="*70)
    print(f"\nTotal files processed: {metrics['total_files']}")
    print(f"Total events extracted: {metrics['total_events']}")
    print(f"Average events per file: {metrics.get('avg_events_per_file', 0)}")

    print("\n" + "-"*70)
    print("Platforms:")
    for platform, count in sorted(metrics['platforms'].items(), key=lambda x: -x[1]):
        print(f"  {platform}: {count} events")

    print("\n" + "-"*70)
    print("Generation types:")
    for gen_type, count in sorted(metrics['generation_types'].items(), key=lambda x: -x[1]):
        print(f"  {gen_type}: {count} events")

    print("\n" + "-"*70)
    print("Teams:")
    for team, count in sorted(metrics['teams'].items(), key=lambda x: -x[1]):
        print(f"  {team}: {count} tasks")

    print("\n" + "-"*70)
    print("Priorities:")
    for priority, count in sorted(metrics['priorities'].items(), key=lambda x: -x[1]):
        print(f"  {priority}: {count} tasks")

    print("\n" + "-"*70)
    print("Task statuses:")
    for status, count in sorted(metrics['statuses'].items(), key=lambda x: -x[1]):
        print(f"  {status}: {count} occurrences")

    print("\n" + "-"*70)
    print(f"Unique tasks: {metrics['unique_task_count']}")
    print(f"Completed tasks: {metrics['completed_tasks']}")
    print(f"Cancelled tasks: {metrics['cancelled_tasks']}")
    print(f"In-progress tasks: {metrics['in_progress_tasks']}")
    print(f"Todo tasks: {metrics['todo_tasks']}")

    print("\n" + "-"*70)
    print("Most active leads:")
    for lead, count in sorted(metrics['leads'].items(), key=lambda x: -x[1])[:5]:
        print(f"  {lead}: {count} task assignments")

    print("\n" + "-"*70)
    print("Slack activity:")
    print(f"  Total unique senders: {metrics['unique_slack_senders_count']}")
    print(f"  Most active senders:")
    for sender, count in sorted(metrics['slack_messages_per_sender'].items(), key=lambda x: -x[1])[:5]:
        print(f"    {sender}: {count} messages")

    print("\n" + "-"*70)
    print("Slack channels:")
    for channel, count in sorted(metrics['slack_messages_per_channel'].items(), key=lambda x: -x[1]):
        print(f"  #{channel}: {count} messages")

    if metrics['tasks_with_lead_changes']:
        print("\n" + "-"*70)
        print(f"Tasks with lead reassignments: {len(metrics['tasks_with_lead_changes'])}")
        for task, num_leads in list(metrics['tasks_with_lead_changes'].items())[:3]:
            print(f"  '{task}': {num_leads} different leads")

    if metrics['tasks_with_deadline_extensions']:
        print("\n" + "-"*70)
        print(f"Tasks with deadline changes: {len(metrics['tasks_with_deadline_extensions'])}")
        for task, num_deadlines in list(metrics['tasks_with_deadline_extensions'].items())[:3]:
            print(f"  '{task}': {num_deadlines} different deadlines")

    if metrics['all_task_durations']:
        print("\n" + "-"*70)
        print("Task completion durations:")
        print(f"  Average: {metrics['avg_task_duration_days']} days")
        print(f"  Minimum: {metrics['min_task_duration_days']} days")
        print(f"  Maximum: {metrics['max_task_duration_days']} days")
        print(f"\n  Completed tasks breakdown:")
        for task_info in metrics['all_task_durations'][:5]:
            print(f"    '{task_info['task']}': {task_info['duration_days']} days ({task_info['start']} → {task_info['end']})")

    print("\n" + "-"*70)
    print("Top 5 busiest dates:")
    sorted_dates = sorted(metrics['events_by_date'].items(), key=lambda x: -x[1])[:5]
    for date, count in sorted_dates:
        print(f"  {date}: {count} events")

    print("\n" + "-"*70)
    print(f"\nFiles saved:")
    print("  - event_metrics.json")
    print("  - all_events_chronological.json")

if __name__ == "__main__":
    main()