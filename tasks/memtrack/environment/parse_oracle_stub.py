#!/usr/bin/env python3
"""
Parse oracle.txt file and extract question answers for stub mode
"""

import sys
import re
from pathlib import Path

def parse_oracle_file(oracle_file: Path, config_file: Path, output_dir: Path, questions_dir: Path):
    """Parse oracle.txt and create log files"""
    
    with open(oracle_file, 'r') as f:
        content = f.read()
    
    # Extract processing log (everything before "Phase 2: Answering Questions")
    processing_match = re.search(r'(.*?)==========================================\s*Phase 2: Answering Questions', content, re.DOTALL)
    if processing_match:
        processing_log = processing_match.group(1)
        processing_log_file = output_dir / "processing.log"
        with open(processing_log_file, 'w') as f:
            f.write(processing_log)
        print(f"Created: {processing_log_file}")
    
    # Extract question answers
    # Pattern: "Processing Question X/Y" ... "Question X completed"
    # Split by "Processing Question" markers
    question_sections = re.split(r'Processing Question (\d+)/(\d+)\s*==========================================', content)
    
    questions = []
    # Skip first section (everything before first question)
    for i in range(1, len(question_sections), 3):
        if i + 2 >= len(question_sections):
            break
            
        question_num = int(question_sections[i])
        question_section = question_sections[i + 2]
        
        # Extract question text (after "Question: ")
        question_match = re.search(r'Question:\s*([^\n]+)', question_section)
        if not question_match:
            continue
        question_text = question_match.group(1).strip()
        
        # Extract answer (everything after "Asking Claude..." until "Question X completed")
        answer_match = re.search(r'Asking Claude\.\.\.\s*(.*?)(?=\s*Question \d+ completed|\s*==========================================\s*All questions processed)', question_section, re.DOTALL)
        if answer_match:
            answer_content = answer_match.group(1).strip()
        else:
            # Fallback: take everything after question
            answer_content = re.sub(r'^.*?Question:\s*[^\n]+\s*', '', question_section, flags=re.DOTALL)
            answer_content = re.sub(r'\s*Question \d+ completed.*$', '', answer_content, flags=re.DOTALL).strip()
        
        # Create question log file
        question_log_file = questions_dir / f"question_{question_num}.log"
        
        # Format similar to what claude would output
        log_content = f"Asking Claude...\n{answer_content}\n"
        
        with open(question_log_file, 'w') as f:
            f.write(log_content)
        
        print(f"Created: {question_log_file} (answer length: {len(answer_content)} chars)")
        questions.append((question_num, question_text, answer_content))
    
    # Create summary file
    summary_file = output_dir / "summary.txt"
    with open(summary_file, 'w') as f:
        f.write("Benchmark Run Summary (STUB MODE)\n")
        f.write("==================================\n\n")
        f.write(f"Configuration: {Path(config_file).stem}\n")
        f.write(f"Total Questions: {len(questions)}\n\n")
        f.write("Questions and Answers:\n")
        f.write("=====================\n\n")
        
        for q_num, q_text, q_answer in questions:
            f.write(f"Question {q_num}:\n")
            f.write(f"{q_text}\n\n")
            f.write(f"Answer:\n{q_answer}\n\n")
            f.write(f"Log File: questions/question_{q_num}.log\n")
            f.write("---\n\n")
    
    print(f"Created: {summary_file}")
    print(f"\n✓ Stub mode: Created logs for {len(questions)} questions")
    
    return len(questions)

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: parse_oracle_stub.py <oracle_file> <config_file> <output_dir> <questions_dir>")
        sys.exit(1)
    
    oracle_file = Path(sys.argv[1])
    config_file = Path(sys.argv[2])
    output_dir = Path(sys.argv[3])
    questions_dir = Path(sys.argv[4])
    
    if not oracle_file.exists():
        print(f"Error: Oracle file not found: {oracle_file}")
        sys.exit(1)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    questions_dir.mkdir(parents=True, exist_ok=True)
    
    parse_oracle_file(oracle_file, config_file, output_dir, questions_dir)
