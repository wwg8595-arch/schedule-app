from flask import Flask, jsonify, request, render_template
import uuid
import os
import database

app = Flask(__name__)

# Initialize database tables on startup
database.init_db()

# Render SPA template for both main landing page and individual rooms
@app.route('/')
@app.route('/room/<room_id>')
def index(room_id=None):
    return render_template('index.html')

# Health check endpoint for Render
@app.route('/health')
def health():
    return jsonify({'status': 'ok'}), 200

# API: Create a new room
@app.route('/api/rooms', methods=['POST'])
def create_room():
    data = request.get_json() or {}
    title = data.get('title', '').strip() or "새로운 모임 일정 조율"
    dates = data.get('dates', [])
    
    if not dates:
        return jsonify({'error': '최소 한 개 이상의 날짜가 필요합니다.'}), 400
        
    room_id = str(uuid.uuid4())
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Insert room
        cursor.execute('INSERT INTO rooms (id, title) VALUES (?, ?)', (room_id, title))
        
        # Insert candidates
        for date_str in dates:
            candidate_id = f"cand-{str(uuid.uuid4())[:8]}"
            cursor.execute('INSERT INTO candidates (id, room_id, date_str) VALUES (?, ?, ?)', 
                           (candidate_id, room_id, date_str))
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'방 생성 실패: {str(e)}'}), 500
    finally:
        conn.close()
        
    return jsonify({'room_id': room_id}), 201

# API: Get room details, candidate dates, and vote counts
@app.route('/api/rooms/<room_id>', methods=['GET'])
def get_room(room_id):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Verify room exists
    room = cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,)).fetchone()
    if not room:
        conn.close()
        return jsonify({'error': '존재하지 않는 방입니다.'}), 404
        
    # Get candidates
    candidates = cursor.execute('SELECT * FROM candidates WHERE room_id = ?', (room_id,)).fetchall()
    
    # Get votes
    votes = cursor.execute('SELECT * FROM votes WHERE room_id = ?', (room_id,)).fetchall()
    
    conn.close()
    
    # Map votes to candidates
    votes_map = {}
    for vote in votes:
        cand_id = vote['candidate_id']
        voter = vote['voter_name']
        if cand_id not in votes_map:
            votes_map[cand_id] = []
        votes_map[cand_id].append(voter)
        
    candidates_list = []
    for cand in candidates:
        cand_id = cand['id']
        date_str = cand['date_str']
        voters = votes_map.get(cand_id, [])
        candidates_list.append({
            'id': cand_id,
            'date_str': date_str,
            'voters': voters
        })
        
    return jsonify({
        'id': room['id'],
        'title': room['title'],
        'candidates': candidates_list
    })

# API: Submit a vote
@app.route('/api/rooms/<room_id>/vote', methods=['POST'])
def vote(room_id):
    data = request.get_json() or {}
    voter_name = data.get('voter_name', '').strip()
    candidate_ids = data.get('candidate_ids', [])
    
    if not voter_name:
        return jsonify({'error': '이름을 입력해 주세요.'}), 400
    if not candidate_ids:
        return jsonify({'error': '투표할 날짜를 한 개 이상 선택해 주세요.'}), 400
        
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if room exists
        room = cursor.execute('SELECT id FROM rooms WHERE id = ?', (room_id,)).fetchone()
        if not room:
            conn.close()
            return jsonify({'error': '존재하지 않는 방입니다.'}), 404
            
        # Validate that selected candidates belong to the room
        valid_candidates = cursor.execute('SELECT id FROM candidates WHERE room_id = ?', (room_id,)).fetchall()
        valid_cand_ids = [c['id'] for c in valid_candidates]
        
        for cid in candidate_ids:
            if cid not in valid_cand_ids:
                conn.close()
                return jsonify({'error': '올바르지 않은 후보 날짜가 포함되어 있습니다.'}), 400
                
        # Check if user already voted for any of the selected dates
        already_voted = []
        for cid in candidate_ids:
            existing = cursor.execute(
                'SELECT id FROM votes WHERE room_id = ? AND candidate_id = ? AND voter_name = ?',
                (room_id, cid, voter_name)
            ).fetchone()
            if existing:
                already_voted.append(cid)
                
        if already_voted:
            conn.close()
            return jsonify({'error': f'이미 해당 날짜에 투표하셨습니다.'}), 409
            
        # Check 8-voter lock for each candidate
        for cid in candidate_ids:
            current_count = cursor.execute(
                'SELECT COUNT(*) as count FROM votes WHERE room_id = ? AND candidate_id = ?',
                (room_id, cid)
            ).fetchone()['count']
            
            if current_count >= 8:
                conn.close()
                return jsonify({'error': '선택하신 후보 중 이미 8명 정원이 마감된 날짜가 있습니다.'}), 423
                
        # Insert votes
        for cid in candidate_ids:
            cursor.execute(
                'INSERT INTO votes (room_id, candidate_id, voter_name) VALUES (?, ?, ?)',
                (room_id, cid, voter_name)
            )
            
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'투표 반영 실패: {str(e)}'}), 500
    finally:
        conn.close()
        
    # Return updated room state
    return get_room(room_id)

# API: Simulate 8 votes to trigger FCFS auto-lock
@app.route('/api/rooms/<room_id>/simulate', methods=['POST'])
def simulate_votes(room_id):
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Check if room exists
        room = cursor.execute('SELECT id FROM rooms WHERE id = ?', (room_id,)).fetchone()
        if not room:
            conn.close()
            return jsonify({'error': '존재하지 않는 방입니다.'}), 404
            
        # Get first candidate
        first_candidate = cursor.execute(
            'SELECT id FROM candidates WHERE room_id = ? ORDER BY date_str ASC LIMIT 1',
            (room_id,)
        ).fetchone()
        
        if not first_candidate:
            conn.close()
            return jsonify({'error': '후보 날짜가 존재하지 않습니다.'}), 404
            
        cid = first_candidate['id']
        
        # Get current voters
        current_voters = cursor.execute(
            'SELECT voter_name FROM votes WHERE room_id = ? AND candidate_id = ?',
            (room_id, cid)
        ).fetchall()
        current_voter_names = [v['voter_name'] for v in current_voters]
        
        # Insert mock votes until count is 8
        mock_names = ['김도윤', '이서연', '박하준', '최지우', '정은우', '강서아', '조도현', '윤하은', '임지민', '한영수', '오순이']
        added_count = 0
        
        for name in mock_names:
            if len(current_voter_names) >= 8:
                break
            if name not in current_voter_names:
                cursor.execute(
                    'INSERT INTO votes (room_id, candidate_id, voter_name) VALUES (?, ?, ?)',
                    (room_id, cid, name)
                )
                current_voter_names.append(name)
                added_count += 1
                
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'error': f'시뮬레이션 투표 실패: {str(e)}'}), 500
    finally:
        conn.close()
        
    return get_room(room_id)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5050))
    app.run(host='0.0.0.0', port=port, debug=True)
