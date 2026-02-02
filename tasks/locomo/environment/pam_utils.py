#!/usr/bin/env python3
"""
PAM Utilities for LoCoMo Benchmark

This module provides utilities for preparing conversation data for PAM processing.
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


def extract_conversation_to_files(sample: Dict, output_dir: str) -> Dict:
    """
    Extract conversation from a locomo sample and save to files for PAM processing.
    
    Args:
        sample: A locomo sample with 'conversation' field
        output_dir: Directory to save the extracted files
    
    Returns:
        Dict with metadata about extracted files
    """
    conversation = sample.get('conversation', {})
    sample_id = sample.get('sample_id', 'unknown')
    
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Extract speaker names
    speaker_a = conversation.get('speaker_a', 'Speaker A')
    speaker_b = conversation.get('speaker_b', 'Speaker B')
    
    # Save speaker info
    speakers_file = output_path / 'speakers.json'
    speakers_data = {
        'speaker_a': speaker_a,
        'speaker_b': speaker_b,
        'sample_id': sample_id
    }
    with open(speakers_file, 'w') as f:
        json.dump(speakers_data, f, indent=2)
    
    # Extract and save each session
    sessions_metadata = []
    session_num = 1
    
    while f'session_{session_num}' in conversation:
        session_key = f'session_{session_num}'
        date_key = f'session_{session_num}_date_time'
        
        session_data = conversation.get(session_key, [])
        session_date = conversation.get(date_key, f'Session {session_num}')
        
        # Save session to file
        session_file = output_path / f'session_{session_num}.json'
        session_content = {
            'session_number': session_num,
            'date_time': session_date,
            'speaker_a': speaker_a,
            'speaker_b': speaker_b,
            'turns': session_data
        }
        
        with open(session_file, 'w') as f:
            json.dump(session_content, f, indent=2)
        
        sessions_metadata.append({
            'session_number': session_num,
            'date_time': session_date,
            'turn_count': len(session_data),
            'file': str(session_file)
        })
        
        session_num += 1
    
    # Save metadata
    metadata_file = output_path / 'metadata.json'
    metadata = {
        'sample_id': sample_id,
        'speaker_a': speaker_a,
        'speaker_b': speaker_b,
        'total_sessions': session_num - 1,
        'sessions': sessions_metadata
    }
    
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    # Create a combined conversation file in markdown format
    conversation_md = output_path / 'conversation_history.md'
    md_content = generate_conversation_markdown(conversation, speaker_a, speaker_b)
    with open(conversation_md, 'w') as f:
        f.write(md_content)
    
    return metadata


def generate_conversation_markdown(conversation: Dict, speaker_a: str, speaker_b: str) -> str:
    """Generate a markdown representation of the conversation."""
    lines = [
        f"# Conversation History",
        f"",
        f"**Participants:** {speaker_a} and {speaker_b}",
        f"",
        "---",
        ""
    ]
    
    session_num = 1
    while f'session_{session_num}' in conversation:
        session_key = f'session_{session_num}'
        date_key = f'session_{session_num}_date_time'
        
        session_data = conversation.get(session_key, [])
        session_date = conversation.get(date_key, f'Session {session_num}')
        
        lines.append(f"## Session {session_num} - {session_date}")
        lines.append("")
        
        for turn in session_data:
            speaker = turn.get('speaker', 'Unknown')
            text = turn.get('text', '')
            dia_id = turn.get('dia_id', '')
            
            lines.append(f"**{speaker}** [{dia_id}]:")
            lines.append(f"> {text}")
            lines.append("")
            
            # Handle image sharing
            if 'blip_caption' in turn:
                lines.append(f"*[Shared image: {turn.get('blip_caption', 'image')}]*")
                lines.append("")
        
        lines.append("---")
        lines.append("")
        session_num += 1
    
    return "\n".join(lines)


def extract_questions(sample: Dict, output_file: str) -> List[Dict]:
    """Extract questions from a locomo sample."""
    questions = sample.get('qa', [])
    
    questions_data = []
    for i, qa in enumerate(questions):
        questions_data.append({
            'question_num': i + 1,
            'question': qa.get('question', ''),
            'expected_answer': str(qa.get('answer', '')),
            'category': qa.get('category', 0),
            'evidence': qa.get('evidence', [])
        })
    
    with open(output_file, 'w') as f:
        json.dump(questions_data, f, indent=2)
    
    return questions_data


def main():
    parser = argparse.ArgumentParser(description='PAM utilities for LoCoMo')
    parser.add_argument('action', choices=['extract', 'questions'],
                        help='Action to perform')
    parser.add_argument('--data-file', type=str, required=True,
                        help='Path to locomo data file')
    parser.add_argument('--sample-index', type=int, default=0,
                        help='Index of sample to process')
    parser.add_argument('--output-dir', type=str, default='./unsorted',
                        help='Output directory')
    parser.add_argument('--questions-file', type=str, default='./questions.json',
                        help='Output file for questions')
    
    args = parser.parse_args()
    
    # Load data
    with open(args.data_file, 'r') as f:
        data = json.load(f)
    
    if args.sample_index >= len(data):
        print(f"Error: Sample index {args.sample_index} out of range (max: {len(data) - 1})")
        return 1
    
    sample = data[args.sample_index]
    
    if args.action == 'extract':
        metadata = extract_conversation_to_files(sample, args.output_dir)
        print(f"Extracted conversation for sample: {metadata['sample_id']}")
        print(f"Total sessions: {metadata['total_sessions']}")
        print(f"Output directory: {args.output_dir}")
        
    elif args.action == 'questions':
        questions = extract_questions(sample, args.questions_file)
        print(f"Extracted {len(questions)} questions to {args.questions_file}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
