import requests
import re
import time
import os

# CONFIGURATION
# Best practice: Load from environment variables for security
SUPABASE_URL = "https://uiddbckrjparmtbdegzx.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." # Keep your key safe!

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"  # Returns the created object including its ID
}

def clean_html_content(file_path):
    print(f"--- Reading {file_path} ---")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: {file_path} not found.")
        return None

def parse_data(html):
    print("Parsing topics and questions...")
    # More robust topic extraction
    topic_names = re.findall(r'"([^"]+)"\s*:\s*\[', html)
    topic_names = list(dict.fromkeys(topic_names))
    
    extracted_data = {}
    for topic in topic_names:
        # Look for the array associated with the topic name
        pattern = rf'"{topic}"\s*:\s*\[(.*?)(?=\n\s*"[^"]+"\s*:\s*\[|\]\s*\}})'
        match = re.search(pattern, html, re.DOTALL)
        
        if match:
            section = match.group(1)
            # Match the {q: "...", a: [...], c: "..."} structure
            q_pattern = r'\{q:\s*"([^"]+)"\s*,\s*a:\s*\[([^\]]+)\]\s*,\s*c:\s*"([^"]+)"\}'
            q_matches = re.findall(q_pattern, section)
            
            questions = []
            for q_text, opts_text, correct in q_matches:
                options = [opt.strip().replace('"', '') for opt in opts_text.split(',')]
                questions.append({
                    'question_text': q_text,
                    'option_a': options[0] if len(options) > 0 else "",
                    'option_b': options[1] if len(options) > 1 else "",
                    'option_c': options[2] if len(options) > 2 else "",
                    'correct_answer': correct
                })
            
            if questions:
                extracted_data[topic] = questions
    
    return extracted_data

def sync_to_supabase(data):
    topic_names = list(data.keys())
    free_topics_count = 5
    
    # 1. Clear Existing Data (Careful: This wipes the tables)
    print("\n[1/3] Cleaning database...")
    requests.delete(f"{SUPABASE_URL}/rest/v1/questions?select=*", headers=HEADERS)
    requests.delete(f"{SUPABASE_URL}/rest/v1/topics?select=*", headers=HEADERS)

    # 2. Insert Topics and get IDs
    print(f"\n[2/3] Inserting {len(topic_names)} topics...")
    topic_mapping = {} # To store name -> id
    
    for i, name in enumerate(topic_names):
        payload = {
            "name": name,
            "is_premium": i >= free_topics_count
        }
        
        try:
            response = requests.post(f"{SUPABASE_URL}/rest/v1/topics", headers=HEADERS, json=payload)
            if response.status_code == 201:
                topic_id = response.json()[0]['id']
                topic_mapping[name] = topic_id
                print(f"  ✓ Created: {name}")
            else:
                print(f"  ✗ Failed topic {name}: {response.text}")
        except Exception as e:
            print(f"  ! Error on {name}: {e}")

    # 3. Batch Insert Questions
    print("\n[3/3] Inserting questions in batches...")
    batch_size = 50
    total_q = 0

    for name, questions in data.items():
        if name not in topic_mapping:
            continue
            
        topic_id = topic_mapping[name]
        # Attach topic_id to every question
        for q in questions:
            q['topic_id'] = topic_id
        
        # Split into chunks for efficiency
        for i in range(0, len(questions), batch_size):
            chunk = questions[i:i + batch_size]
            try:
                resp = requests.post(f"{SUPABASE_URL}/rest/v1/questions", headers=HEADERS, json=chunk)
                if resp.status_code in [200, 201]:
                    total_q += len(chunk)
                else:
                    print(f"  ✗ Batch failed for {name}: {resp.text}")
            except Exception as e:
                print(f"  ! Connection error: {e}")
        
        print(f"  ✓ {name}: Uploaded questions")

    return len(topic_mapping), total_q

def main():
    html_content = clean_html_content("dvtheory.html")
    if not html_content:
        return

    data = parse_data(html_content)
    print(f"Found {len(data)} topics.")

    confirm = input("\nReady to sync to Supabase? (type 'yes'): ")
    if confirm.lower() == 'yes':
        start_time = time.time()
        topics_count, questions_count = sync_to_supabase(data)
        duration = round(time.time() - start_time, 2)
        
        print(f"\n{'='*40}")
        print(f"SUCCESS: {topics_count} Topics | {questions_count} Questions")
        print(f"Time elapsed: {duration} seconds")
        print(f{'='*40}")
    else:
        print("Operation cancelled.")

if __name__ == "__main__":
    main()
