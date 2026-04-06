from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

statePath = os.path.join(os.path.dirname(__file__), 'hueLocalState.json')
state: Dict[str, Any] = {
	'username': None,
    'port': 5057,
    'favoriteRooms': None,
	'updatedAt': None,
}

@app.after_request
def addCorsHeaders(resp):
	resp.headers['Access-Control-Allow-Origin'] = '*'
	resp.headers['Access-Control-Allow-Methods'] = 'GET,POST,PUT,OPTIONS'
	resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
	resp.headers['Access-Control-Max-Age'] = '86400'
	return resp

@app.route('/<path:path>', methods=['OPTIONS'])
def corsPreflight(path):
	return ('', 204)

def loadState() -> None:
	try:
		with open(statePath, 'r', encoding='utf-8') as f:
			data = json.load(f)
			if isinstance(data, dict):
				state.update(data)
	except Exception:
		pass

def saveState() -> None:
	state['updatedAt'] = int(time.time())
	with open(statePath, 'w', encoding='utf-8') as f:
		json.dump(state, f, ensure_ascii=False, indent=2)

def errorReturned(answer: Any) -> bool:
	return isinstance(answer, list) and len(answer) > 0 and isinstance(answer[0], dict) and 'error' in answer[0]

def getBridgeIp() -> str:
	bridgeIp = (request.args.get('bridgeIp') or '').strip()
	if not bridgeIp:
		raise ValueError('bridgeIp missing')
	return bridgeIp

def hueUrl(bridgeIp: str, path: str = '') -> str:
	path = path.lstrip('/')
	if path:
		return f'http://{bridgeIp}/api/{path}'
	return f'http://{bridgeIp}/api'

def hueRequest(bridgeIp: str, method: str, path: str = '', body: Optional[Dict[str, Any]] = None) -> Any:
	path = path.lstrip('/')

	http_url = f'http://{bridgeIp}/api' + (f'/{path}' if path else '')
	try:
		r = requests.request(
			method=method,
			url=http_url,
			json=body,
			timeout=5,
			allow_redirects=False
		)
		if r.status_code in (301, 302, 307, 308):
			raise RuntimeError('redirect_to_https')

		return r.json()
	except Exception:
		https_url = f'https://{bridgeIp}/api' + (f'/{path}' if path else '')
		try:
			r = requests.request(
				method=method,
				url=https_url,
				json=body,
				timeout=5,
				verify=False
			)
			return r.json()
		except Exception as e:
			return [{
				'error': {
					'type': 9999,
					'description': f'connect_failed: {type(e).__name__}: {str(e)}'
				}
			}]

def validateUsername(bridgeIp: str, username: str) -> bool:
	answer = hueRequest(bridgeIp, 'GET', username)
	return not errorReturned(answer)

def createUsername(bridgeIp: str) -> Dict[str, Any]:
	answer = hueRequest(bridgeIp, 'POST', '', body={ 'devicetype': 'xeneon_edge_widget#corsair' })

	if errorReturned(answer):
		return { 'ok': False, 'error': answer[0]['error'] }

	first = answer[0] if isinstance(answer, list) and answer else None
	if isinstance(first, dict) and 'success' in first and isinstance(first['success'], dict) and 'username' in first['success']:
		return { 'ok': True, 'username': first['success']['username'] }

	return { 'ok': False, 'error': { 'type': 9998, 'description': 'unexpected_response', 'raw': answer } }

def requireUsername() -> str:
	username = str(state.get('username') or '').strip()
	if not username:
		raise ValueError('not paired (no username stored)')
	return username

def isRoomFavorite(roomId) -> bool:
	if not isinstance(state.get('favoriteRooms'), list):
		saveState()
		return False

	favorites = state.get('favoriteRooms')
	return str(roomId) in favorites

def favRoom(roomId):
	favs = state.setdefault('favoriteRooms', [])
	favs.append(str(roomId))
	state['favoriteRooms'] = favs
	saveState()

def unfavRoom(roomId):
	favs = state.setdefault('favoriteRooms', [])
	if favs:
		favs.remove(str(roomId))

	state['favoriteRooms'] = favs
	saveState()

@app.get('/health')
def health():
	return jsonify({
		'ok': True,
		'paired': bool(str(state.get('username') or '').strip()),
		'username': state.get('username'),
		'port': state.get('port'),
		'updatedAt': state.get('updatedAt')
	})

@app.post('/setUsername')
def setUsername():
	username = (request.args.get('username') or '').strip()
	if not username:
		return jsonify({ 'ok': False, 'error': 'username missing' }), 400

	state['username'] = username
	saveState()
	return jsonify({ 'ok': True, 'username': username })

@app.post('/ensurePaired')
def ensurePaired():
	bridgeIp = getBridgeIp()

	username = str(state.get('username') or '').strip()
	if username:
		if validateUsername(bridgeIp, username):
			return jsonify({ 'ok': True, 'paired': True, 'username': username })
		state['username'] = None
		saveState()

	result = createUsername(bridgeIp)
	if result.get('ok'):
		state['username'] = result['username']
		saveState()
		return jsonify({ 'ok': True, 'paired': True, 'username': state['username'] })

	return jsonify({ 'ok': False, 'paired': False, 'error': result.get('error') }), 400

@app.post('/favorite/<room_id>')
def favorite(room_id: str):
	if isRoomFavorite(room_id):
		unfavRoom(room_id)
	else:
		favRoom(room_id)
	return jsonify({ 'ok': True, 'roomId': room_id, 'favorite': isRoomFavorite(room_id) })

@app.get('/rooms')
def rooms():
	bridgeIp = getBridgeIp()
	username = requireUsername()

	groups = hueRequest(bridgeIp, 'GET', f'{username}/groups')
	if not isinstance(groups, dict):
		return jsonify({ 'ok': False, 'error': 'groups_invalid', 'raw': groups }), 502

	# Récupère toutes les lights UNE fois, pour calculer la moyenne par room
	lightsAll = hueRequest(bridgeIp, 'GET', f'{username}/lights')
	if not isinstance(lightsAll, dict):
		return jsonify({ 'ok': False, 'error': 'lights_invalid', 'raw': lightsAll }), 502

	roomsOut = []
	for gid, g in groups.items():
		if not isinstance(g, dict):
			continue

		gtype = g.get('type')
		if gtype not in ['Room', 'Zone']:
			continue

		lightIds = [str(x) for x in (g.get('lights') or [])]

		# Calcul bri moyenne
		briValues = []
		anyOn = False

		for lid in lightIds:
			ld = lightsAll.get(lid)
			if not isinstance(ld, dict):
				continue

			st = ld.get('state') or {}
			if 'reachable' in st and not bool(st.get('reachable')):
				continue

			if bool(st.get('on')):
				anyOn = True

			briRaw = st.get('bri')
			if isinstance(briRaw, (int, float)):
				briValues.append(int(briRaw))

		# Si pas de bri dispo, on met un défaut “safe”
		if briValues:
			avgBri = int(round(sum(briValues) / len(briValues)))
			if avgBri < 1: avgBri = 1
			if avgBri > 254: avgBri = 254
		else:
			avgBri = 1

		avgPct = int(round((avgBri / 254) * 100))
		if avgPct < 1: avgPct = 1
		if avgPct > 100: avgPct = 100

		roomsOut.append({
			'id': str(gid),
			'name': g.get('name', f'Room {gid}'),
			'favorite': isRoomFavorite(gid),
			'type': gtype,
			'lightIds': lightIds,
			'bri': avgBri,
			'briPct': avgPct,
			'anyOn': anyOn
		})

	roomsOut.sort(key=lambda x: x['name'])
	return jsonify({ 'ok': True, 'rooms': roomsOut })

@app.get('/scenes')
def scenes():
	bridgeIp = getBridgeIp()
	username = requireUsername()

	scenes = hueRequest(bridgeIp, 'GET', f'{username}/scenes')
	if not isinstance(scenes, dict):
		return jsonify({ 'ok': False, 'error': 'scenes_invalid', 'raw': scenes }), 502

	scenesOut = []
	for sid, scene in scenes.items():
		if not isinstance(scene, dict):
			continue

		scenesOut.append({
			'id': str(sid),
			'name': scene.get('name'),
			'group': scene.get('group'),
			'type': 'scene'
		})

	scenesOut.sort(key=lambda x: x['name'])
	return jsonify({ 'ok': True, 'scenes': scenesOut })

@app.get('/rooms/<room_id>/lights')
def roomLights(room_id: str):
	bridgeIp = getBridgeIp()
	username = requireUsername()

	group = hueRequest(bridgeIp, 'GET', f'{username}/groups/{room_id}')
	if not isinstance(group, dict):
		return jsonify({ 'ok': False, 'error': 'group_invalid', 'raw': group }), 502

	lightIds = [str(x) for x in (group.get('lights') or [])]

	lightsAll = hueRequest(bridgeIp, 'GET', f'{username}/lights')
	if not isinstance(lightsAll, dict):
		return jsonify({ 'ok': False, 'error': 'lights_invalid', 'raw': lightsAll }), 502

	lights = []
	for lid in lightIds:
		l = lightsAll.get(lid)
		if not isinstance(l, dict):
			continue
		st = l.get('state') or {}
		bri = st.get('bri')
		lights.append({
			'id': lid,
			'name': l.get('name', f'Light {lid}'),
			'on': bool(st.get('on')),
            'bri': int(bri) if isinstance(bri, int) else None,
			'reachable': True if 'reachable' not in st else bool(st.get('reachable'))
		})

	lights.sort(key=lambda x: x['name'])
	return jsonify({
		'ok': True,
		'room': { 'id': room_id, 'name': group.get('name', f'Room {room_id}') },
		'lights': lights
	})

@app.post('/scenes/<room_id>/<scene_id>')
def roomSceneRecall(room_id: str, scene_id: str):
	bridgeIp = getBridgeIp()
	username = requireUsername()

	res = hueRequest(
		bridgeIp,
		'PUT',
		f'{username}/groups/{room_id}/action',
        body={ 'scene': scene_id }
	)

	return jsonify({ 'ok': True })

@app.post('/lights/<light_id>/brightness/<int:bri>')
def setBrightness(light_id: str, bri: int):
	bridgeIp = getBridgeIp()
	username = requireUsername()

	if bri < 1: bri = 1
	if bri > 254: bri = 254

	body = { 'bri': bri }

	body['on'] = True

	res = hueRequest(bridgeIp, 'PUT', f'{username}/lights/{light_id}/state', body=body)
	if errorReturned(res):
		return jsonify({ 'ok': False, 'error': res[0]['error'] }), 502

	return jsonify({ 'ok': True, 'lightId': str(light_id), 'bri': bri })

@app.post('/lights/<light_id>/toggle')
def toggle(light_id: str):
	bridgeIp = getBridgeIp()
	username = requireUsername()

	light = hueRequest(bridgeIp, 'GET', f'{username}/lights/{light_id}')
	if not isinstance(light, dict):
		return jsonify({ 'ok': False, 'error': 'light_invalid', 'raw': light }), 502

	currentOn = bool(((light.get('state') or {}).get('on')))
	nextOn = not currentOn

	res = hueRequest(bridgeIp, 'PUT', f'{username}/lights/{light_id}/state', body={ 'on': nextOn })
	if errorReturned(res):
		return jsonify({ 'ok': False, 'error': res[0]['error'] }), 502

	return jsonify({ 'ok': True, 'lightId': light_id, 'on': nextOn })

@app.post('/rooms/<room_id>/all/<state>')
def roomAll(room_id: str, state: str):
	bridgeIp = getBridgeIp()
	username = requireUsername()

	if state not in ('on', 'off'):
		return jsonify({ 'ok': False, 'error': 'invalid_state' }), 400

	res = hueRequest(
		bridgeIp,
		'PUT',
		f'{username}/groups/{room_id}/action',
		body={ 'on': (state == 'on') }
	)

	if errorReturned(res):
		return jsonify({ 'ok': False, 'error': res[0]['error'] }), 502

	return jsonify({ 'ok': True, 'roomId': room_id, 'on': (state == 'on') })

@app.post('/rooms/<room_id>/brightness/<int:bri>')
def setRoomBrightness(room_id: str, bri: int):
	bridgeIp = getBridgeIp()
	username = requireUsername()

	if bri < 1:
		bri = 1
	if bri > 254:
		bri = 254

	res = hueRequest(
		bridgeIp,
		'PUT',
		f'{username}/groups/{room_id}/action',
		body={ 'bri': bri, 'on': True }
	)

	if errorReturned(res):
		return jsonify({ 'ok': False, 'error': res[0]['error'] }), 502

	return jsonify({ 'ok': True, 'roomId': room_id, 'bri': bri })

if __name__ == '__main__':
	print(f"Hue Local Service started. Listening on port {state.get('port')}")
	loadState()
	app.run(host='127.0.0.1', port=state.get('port'))
