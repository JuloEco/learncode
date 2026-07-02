from flask import Flask, render_template_string, request, jsonify, redirect, session, url_for
import json
import os
import ast
import sqlite3
from datetime import datetime
import math



app = Flask(__name__)
app.secret_key = "learncode_PRO_v10_fixed"

def mini_editor_html(editor_id, content=""):
    """Génère le HTML du mini éditeur de texte enrichi (mini Word)."""
    content = content or ""
    return f'''<div class="mini-word">
      <div class="mini-toolbar">
        <button type="button" onclick="miniExec('{editor_id}','bold')" title="Gras"><b>G</b></button>
        <button type="button" onclick="miniExec('{editor_id}','italic')" title="Italique"><i>I</i></button>
        <button type="button" onclick="miniExec('{editor_id}','underline')" title="Souligné"><u>S</u></button>
        <select onchange="if(this.value){{miniExec('{editor_id}','fontName', this.value)}}">
            <option value="">Police</option>
            <option value="Plus Jakarta Sans">Défaut</option>
            <option value="Georgia">Georgia</option>
            <option value="Courier New">Courier New</option>
            <option value="Comic Sans MS">Comic Sans</option>
            <option value="Impact">Impact</option>
        </select>
        <button type="button" onclick="miniExec('{editor_id}','insertUnorderedList')" title="Liste à puces">• Liste</button>
        <button type="button" onclick="miniExec('{editor_id}','formatBlock','H2')" title="Titre">Titre</button>
        <button type="button" onclick="miniExec('{editor_id}','formatBlock','P')" title="Paragraphe">Texte</button>
        <button type="button" onclick="miniInsertImage('{editor_id}')" title="Insérer une image">🖼 Image</button>
        <input type="file" id="{editor_id}-file" accept="image/*" style="display:none" onchange="miniHandleImage('{editor_id}', this)">
      </div>
      <div id="{editor_id}" class="mini-content" contenteditable="true" data-placeholder="Écrivez ici...">{content}</div>
    </div>'''

app.jinja_env.globals.update(enumerate_list=enumerate, mini_editor=mini_editor_html)

# --- BASE DE DONNÉES (SQLite) ---
DB_FILE = "learncode.db"
LEGACY_JSON_FILE = "learncode_v6.json"  # ancien format, utilisé uniquement pour la migration automatique
TABLES = ["cours", "users", "devoirs", "cartes", "documents"]

def get_level_data(xp):
    # Formule : on monte de niveau tous les 100 XP (tu peux ajuster)
    level = (xp // 100) + 1
    current_level_xp = xp % 100
    progress = current_level_xp  # Car un niveau fait 100 XP
    return {"lvl": level, "progress": progress, "next": 100}

def get_conn():
    """Ouvre une connexion SQLite. Le mode WAL autorise des lectures concurrentes
    pendant une écriture et protège contre la corruption en cas de coupure."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    conn = get_conn()
    try:
        with conn:
            for t in TABLES:
                conn.execute(f"""
                    CREATE TABLE IF NOT EXISTS {t} (
                        id TEXT PRIMARY KEY,
                        data TEXT NOT NULL,
                        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                    )
                """)
    finally:
        conn.close()

def _read_all():
    conn = get_conn()
    try:
        result = {}
        for t in TABLES:
            rows = conn.execute(f"SELECT id, data FROM {t}").fetchall()
            result[t] = {rid: json.loads(data) for rid, data in rows}
        return result
    finally:
        conn.close()

def _write_all(data):
    """Réécrit intégralement chaque table dans une seule transaction atomique :
    soit tout est enregistré, soit rien ne l'est (jamais de fichier à moitié écrit)."""
    conn = get_conn()
    try:
        with conn:
            for t in TABLES:
                conn.execute(f"DELETE FROM {t}")
                rows = [
                    (rid, json.dumps(val, ensure_ascii=False), datetime.now().isoformat())
                    for rid, val in data.get(t, {}).items()
                ]
                if rows:
                    conn.executemany(f"INSERT INTO {t} (id, data, updated_at) VALUES (?, ?, ?)", rows)
    finally:
        conn.close()

def load_db():
    init_db()
    result = _read_all()

    # Migration automatique et unique depuis l'ancien fichier JSON (learncode_v6.json)
    # si la base SQLite est encore vide et que l'ancien fichier existe.
    if not any(result.values()) and os.path.exists(LEGACY_JSON_FILE):
        try:
            with open(LEGACY_JSON_FILE, "r", encoding="utf-8") as f:
                legacy = json.load(f)
            for t in TABLES:
                result[t] = legacy.get(t, {})
            _write_all(result)
            print(f"✅ Migration automatique : {LEGACY_JSON_FILE} → {DB_FILE}")
        except Exception as e:
            print(f"⚠️ Migration depuis {LEGACY_JSON_FILE} impossible : {e}")

    for t in TABLES:
        result.setdefault(t, {})
    return result

def compter_notifs(user):
    count = 0
    for d in DEVOIRS.values():
        rendu = d["rendus"].get(user)
        # On compte si le devoir est corrigé (note présente) mais pas encore vu
        if rendu and rendu.get("note") is not None and rendu.get("vu") == False:
            count += 1
    return count

DB = load_db()
COURS, USERS, DEVOIRS = DB["cours"], DB["users"], DB["devoirs"]
CARTES, DOCUMENTS = DB["cartes"], DB["documents"]

def save_db():
    _write_all({
        "cours": COURS,
        "users": USERS,
        "devoirs": DEVOIRS,
        "cartes": CARTES,
        "documents": DOCUMENTS,
    })





# --- DESIGN SYSTEM ---
LAYOUT = r"""
<!DOCTYPE html>
<html lang="fr">
<head>
      <meta charset="UTF-8">
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <title>LearnCode PRO</title>
      <!-- Remplacez la ligne existante par celle-ci -->
      <link rel="icon" type="image/png" href="{{ url_for('static', filename='logo1.png') }}">
      <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
      <script src="https://cdn.jsdelivr.net/pyodide/v0.25.0/full/pyodide.js"></script>
      <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
      <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;600;800&display=swap" rel="stylesheet">
      <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.6.0/dist/confetti.browser.min.js"></script>
      <style>
            :root { 
                  --bg: #050608; --card: #0f1115; --text: #f1f1f1; --text-dim: #71717a;
                  --primary: #6366f1; --secondary: #a855f7; --accent: #22d3ee;
                  --success: #10b981; --danger: #f43f5e; --warning: #fbbf24;
                  --border: rgba(255,255,255,0.08);
            }
            * { box-sizing: border-box; }
            body { background: var(--bg); color: var(--text); font-family: 'Plus Jakarta Sans', sans-serif; margin: 0; }
            .navbar { height: 75px; background: rgba(5, 6, 8, 0.8); backdrop-filter: blur(15px); border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; padding: 0 40px; position: sticky; top: 0; z-index: 1000; }
            .logo { font-weight: 800; font-size: 1.5rem; color: #fff; text-decoration: none; }
            .logo span { color: var(--primary); }
            .nav-links { display: flex; gap: 25px; align-items: center; }
            .nav-links a { color: var(--text-dim); text-decoration: none; font-size: 0.9rem; font-weight: 600; transition: 0.2s; }
            .nav-links a:hover { color: #fff; }
            .wrapper { max-width: 1100px; margin: 40px auto; padding: 0 25px; min-height: 85vh; }
            .glass-card { background: var(--card); border: 1px solid var(--border); border-radius: 24px; padding: 35px; margin-bottom: 30px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5); }
            .btn { padding: 14px 28px; border-radius: 16px; border: none; font-weight: 700; cursor: pointer; transition: 0.3s; display: inline-flex; align-items: center; justify-content: center; gap: 10px; font-size: 0.95rem; text-decoration: none; }
            .btn-primary { background: var(--primary); color: #fff; }
            .btn-primary:hover { transform: translateY(-3px); box-shadow: 0 10px 25px rgba(99, 102, 241, 0.4); }
            .btn-outline { background: transparent; border: 1.5px solid var(--border); color: #fff; }
            input, textarea, select { width: 100%; background: #000; border: 1.5px solid var(--border); padding: 16px; border-radius: 16px; color: #fff; margin: 12px 0 24px 0; font-family: inherit; font-size: 1rem; outline: none; }
            /* Badge de notification dans la Nav */
.nav-link-container { position: relative; display: inline-block; }
.notif-badge {
    position: absolute; top: -8px; right: -12px;
    background: var(--danger); color: white;
    font-size: 0.65rem; padding: 2px 7px;
    border-radius: 10px; font-weight: 800;
    box-shadow: 0 0 10px rgba(244, 63, 94, 0.5);
}

/* Statuts des devoirs */
.status-pill {
    padding: 4px 12px; border-radius: 20px;
    font-size: 0.7rem; font-weight: 800; text-transform: uppercase;
}
.status-todo { background: rgba(251, 191, 36, 0.1); color: var(--warning); }
.status-pending { background: rgba(99, 102, 241, 0.1); color: var(--primary); }
.status-done { background: rgba(16, 185, 129, 0.1); color: var(--success); }

#moteur-genially  .nav-notif {
    background: var(--danger);
    color: white;
    font-size: 0.7rem;
    padding: 2px 6px;
    border-radius: 50%;
    position: absolute;
    top: -10px;
    right: -15px;
    font-weight: 800;
    
}
.nav-link-container { position: relative; 
    font-size: 1.15rem; 
    line-height: normal; 
    color: #d4d4d8; 
    white-space: pre-line; /* PREND EN COMPTE LES RETOURS À LA LIGNE */
    position: relative; 
    display: inline-flex; /* Change inline-block pour inline-flex */
    align-items: center;  /* Centre verticalement le texte et le badge */
    height: 100%;         /* S'assure de prendre toute la hauteur de la nav */

}
/* Remplace ton bloc .badge-grid par celui-ci */
.badge-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); /* Légèrement plus large */
    gap: 20px;
    margin-top: 20px;
}

.badge-card {
    background: #161920; /* Fond plus sombre comme la V1 */
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 25px 15px;
    text-align: center;
    transition: all 0.3s ease;
    display: flex;
    flex-direction: column;
    align-items: center;
}

.badge-card:hover {
    transform: translateY(-8px);
    border-color: var(--primary);
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
}

.badge-icon {
    font-size: 2.5rem;
    margin-bottom: 15px;
    filter: drop-shadow(0 0 10px rgba(255,255,255,0.1));
}

.badge-name {
    font-size: 0.8rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 8px;
    color: #fff; /* Nom en blanc par défaut */
}

.badge-desc {
    font-size: 0.7rem;
    color: var(--text-dim);
    line-height: 1.4;
}
            /* Barre de niveau sur le Dashboard */
.level-container { margin-bottom: 40px; background: var(--card); padding: 20px; border-radius: 20px; border: 1px solid var(--border); }
.level-info { display: flex; justify-content: space-between; margin-bottom: 10px; font-weight: 800; }
.xp-bar-bg { width: 100%; height: 12px; background: #1a1b1e; border-radius: 10px; overflow: hidden; }
.xp-bar-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--accent)); transition: width 1s cubic-bezier(0.22, 1, 0.36, 1); }

/* Animation Level Up */
#level-up-overlay {
    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
    background: rgba(5, 6, 8, 0.9);
    display: none; flex-direction: column; align-items: center; justify-content: center;
    z-index: 10000; animation: fadeIn 0.5s;
}
.lvl-text { font-size: 5rem; font-weight: 900; color: var(--accent); text-shadow: 0 0 30px var(--accent); margin: 0; }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
            /* --- GENIALLY MOTEUR --- */
            .gen-reveal { background: rgba(99, 102, 241, 0.05); border: 2px dashed var(--primary); padding: 30px; border-radius: 20px; text-align: center; cursor: pointer; color: var(--primary); font-weight: 800; margin: 25px 0; transition: 0.3s; }
            .gen-reveal:hover { background: rgba(99, 102, 241, 0.1); }
            /* --- NOUVEAU STYLE DEFINITION (TOOLTIP) --- */
        .gen-hotspot { 
            position: relative; 
            color: var(--accent); 
            border-bottom: 2px dashed var(--accent); 
            cursor: help; 
            font-weight: 700; 
            transition: 0.3s;
            display: inline-block; /* Nécessaire pour le positionnement de la bulle */
        }

        .gen-hotspot:hover {
            color: #fff;
            border-bottom-style: solid;
            text-shadow: 0 0 10px var(--accent);
        }

        /* La bulle (cachée par défaut) */
        .gen-hotspot::after {
            content: attr(data-content); /* Récupère la définition */
            position: absolute;
            bottom: 125%; /* Positionne au-dessus du mot */
            left: 50%;
            transform: translateX(-50%) translateY(10px);
            width: 250px; /* Largeur de la bulle */
            padding: 15px;
            background: #161920; /* Fond carte sombre */
            color: #fff;
            font-size: 0.85rem;
            font-weight: 400;
            line-height: 1.5;
            text-align: center;
            border-radius: 12px;
            border: 1px solid var(--border);
            box-shadow: 0 15px 35px rgba(0,0,0,0.7), 0 0 15px rgba(34, 211, 238, 0.15); /* Lueur accent */
            
            /* Effet d'apparition */
            opacity: 0;
            visibility: hidden;
            transition: transform 0.3s ease, opacity 0.3s ease;
            z-index: 100;
            pointer-events: none; /* Empêche de bloquer la souris */
        }

        /* La petite flèche en bas de la bulle */
        .gen-hotspot::before {
            content: '';
            position: absolute;
            bottom: 110%;
            left: 50%;
            transform: translateX(-50%) translateY(10px);
            border-width: 8px;
            border-style: solid;
            border-color: var(--border) transparent transparent transparent;
            
            /* Effet d'apparition sync */
            opacity: 0;
            visibility: hidden;
            transition: transform 0.3s ease, opacity 0.3s ease;
            z-index: 101;
        }

        /* Affichage au survol */
        .gen-hotspot:hover::after, .gen-hotspot:hover::before {
            opacity: 1;
            visibility: visible;
            transform: translateX(-50%) translateY(0);
        }
            .gen-blur { filter: blur(10px); transition: 0.6s; cursor: pointer; user-select: none; display: inline-block; }
            .gen-blur:hover { filter: blur(0); }
            .gen-tip { padding: 20px; border-radius: 16px; border-left: 6px solid var(--success); background: rgba(16,185,129,0.05); color: #fff; margin: 20px 0; }
            .gen-alert { padding: 20px; border-radius: 16px; border-left: 6px solid var(--danger); background: rgba(244,63,94,0.05); color: #fff; margin: 20px 0; }
            .gen-kbd { background: #27272a; padding: 4px 10px; border-radius: 8px; font-family: monospace; font-size: 0.9em; border-bottom: 4px solid #000; margin: 0 3px; }
            #toast {
    position: fixed; bottom: 20px; right: 20px; 
    background: var(--success); color: white; padding: 15px 30px; 
    border-radius: 12px; transform: translateY(100px); transition: 0.5s; z-index: 9999;
}
#toast.show { transform: translateY(0); }
            /* UI */
            .rank-item { display: flex; align-items: center; justify-content: space-between; padding: 18px 24px; background: rgba(255,255,255,0.02); border-radius: 18px; margin-bottom: 12px; }
            .rank-item.active { border: 1px solid var(--primary); background: rgba(99, 102, 241, 0.1); }
            #code-editor { height: 320px; font-family: 'Fira Code', monospace; background: #020203; color: #7dd3fc; border: 1px solid var(--border); padding: 20px; border-radius: 20px; line-height: 1.6; }
            #console { background: #000; color: #fff; padding: 20px; border-radius: 20px; margin-top: 15px; border-left: 5px solid var(--primary); font-family: monospace; }
            .progress-bar { width: 100%; height: 10px; background: var(--border); border-radius: 20px; overflow: hidden; margin: 12px 0; }
            .progress-fill { height: 100%; background: var(--primary); transition: 1.5s cubic-bezier(0.19, 1, 0.22, 1); }

            /* --- CARTES MENTALES --- */
            .carte-toolbar { display: flex; gap: 10px; flex-wrap: wrap; }
            .carte-canvas-wrap { position: relative; width: 100%; height: 620px; overflow: auto; background:
                radial-gradient(circle, rgba(255,255,255,0.06) 1px, transparent 1px) 0 0/22px 22px, #0b0c10; }
            .carte-node { position: absolute; padding: 14px 20px; border-radius: 14px; min-width: 130px; max-width: 240px;
                box-shadow: 0 8px 20px rgba(0,0,0,0.45); font-weight: 700; font-size: 0.9rem; color: #fff;
                border: 2px solid rgba(255,255,255,0.18); user-select: none; }
            .carte-node .node-text { outline: none; word-break: break-word; }
            .carte-node .node-tools { display: flex; gap: 8px; margin-top: 10px; opacity: 0.85; }
            .carte-node .node-tools span { cursor: pointer; font-size: 0.75rem; }
            .carte-card { background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 25px; transition: 0.3s; }
            .carte-card:hover { border-color: var(--primary); transform: translateY(-4px); }
            .doc-chip { display: inline-flex; align-items: center; gap: 6px; background: rgba(99,102,241,0.1); color: var(--primary);
                border: 1px solid rgba(99,102,241,0.3); padding: 6px 14px; border-radius: 20px; font-size: 0.8rem; font-weight: 700;
                text-decoration: none; margin: 4px 6px 4px 0; }
            .doc-chip.carte { background: rgba(168,85,247,0.1); color: var(--secondary); border-color: rgba(168,85,247,0.3); }

            /* --- MINI WORD (éditeur de documents) --- */
            .mini-word { border: 1px solid var(--border); border-radius: 16px; overflow: hidden; background: #000; margin: 12px 0 24px 0; }
            .mini-toolbar { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--border); }
            .mini-toolbar button, .mini-toolbar select { background: #161920; border: 1px solid var(--border); color: #fff;
                border-radius: 8px; padding: 6px 12px; font-size: 0.8rem; cursor: pointer; margin: 0; width: auto; }
            .mini-toolbar button:hover { border-color: var(--primary); color: var(--primary); }
            .mini-content { min-height: 220px; max-height: 500px; overflow-y: auto; padding: 20px; outline: none; line-height: 1.6; }
            .mini-content img { max-width: 100%; border-radius: 10px; margin: 10px 0; }
            .mini-content:empty:before { content: attr(data-placeholder); color: var(--text-dim); }
            .doc-render { padding: 25px; background: rgba(255,255,255,0.02); border: 1px solid var(--border); border-radius: 18px; line-height: 1.7; }
            .doc-render img { max-width: 100%; border-radius: 10px; margin: 10px 0; }
      </style>
</head>
<body>

<nav class="navbar">
      <a href="/" class="logo">LEARN<span>CODE</span></a>
      <div class="nav-links">
    {% if session.user %}
        <a href="/dashboard">Modules</a>
        <a href="/projet">Sandbox</a>
        <a href="/cartes">Cartes Mentales</a>
        <a href="/stats">Performances</a>
        
        {% if session.user == 'LearnCodePRO' %}
            <a href="/admin" style="color:var(--warning)">Admin</a>
            <a href="/casier" style="color:var(--accent)">Casier</a>
            <a href="/admin/cartes" style="color:var(--secondary)">Gérer Cartes</a>
            <a href="/admin/documents" style="color:var(--secondary)">Documents</a>
        {% else %}
            <div class="nav-link-container">
                <a href="/devoirs">Devoirs</a>
                {% if notifs and notifs > 0 %}
                    <span class="notif-badge">{{ notifs }}</span>
                {% endif %}
            </div>
        {% endif %}
        <a href="/logout" style="color:var(--danger)">Quitter</a>
    {% endif %}
</div>
        
        
    
</div>
</nav>

<div class="wrapper">
      {% if page == 'dashboard' %}
            <h1 style="font-size: 2.8rem; margin-bottom: 8px;">Tableau de bord</h1>
            <p style="color: var(--text-dim); margin-bottom: 40px;">Continuez votre ascension vers la maîtrise du code.</p>
            <div class="level-container">
    <div class="level-info">
        <span>NIVEAU <span style="color:var(--accent)">{{ lvl.lvl }}</span></span>
        <span style="color:var(--text-dim)">{{ lvl.progress }} / {{ lvl.next }} XP</span>
    </div>
    <div class="xp-bar-bg">
        <div class="xp-bar-fill" style="width: {{ lvl.progress }}%"></div>
    </div>
</div>
            {% for cat, items in categories.items() %}
                  <div style="margin-bottom: 60px;">
                        <h2 style="font-size: 0.9rem; text-transform: uppercase; letter-spacing: 2px; color: var(--primary); margin-bottom: 25px;">{{ cat }}</h2>
                        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 25px;">
                              {% for id, info in items %}
                                    <div class="glass-card" style="margin-bottom: 0; padding: 30px; display: flex; flex-direction: column;">
                                          <h3 style="margin-top: 0;">{{ info.titre }}</h3>
                                          {% if id in user_data.notes %}
                                                <div class="progress-bar"><div class="progress-fill" style="width: {{ user_data.notes[id] }}%"></div></div>
                                                <span style="font-size: 0.8rem; color: var(--success); font-weight: 800;">Score: {{ user_data.notes[id] }}%</span>
                                          {% else %}
                                                <p style="font-size: 0.8rem; color: var(--text-dim);">Prêt à commencer</p>
                                          {% endif %}
                                          <a href="/cours/{{ id }}" class="btn btn-primary" style="margin-top: 25px;">Ouvrir le module</a>
                                    </div>
                              {% endfor %}
                        </div>
                  </div>
            {% endfor %}
        {% elif page == 'devoirs_eleve' %}
    <h1 style="font-size: 2.5rem; margin-bottom: 30px;">Mes Devoirs</h1>
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 25px;">
        {% for did, d in devoirs.items() %}
            <div class="glass-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 15px;">
                    <h3 style="margin: 0;">{{ d.titre }} {% if d.get('type') == 'code' %}<span title="Exercice de code">🐍</span>{% endif %}</h3>
                    {% if user in d.rendus %}
                        {% if d.rendus[user].note %}
                            <span class="status-pill status-done">Corrigé ✨</span>
                        {% else %}
                            <span class="status-pill status-pending">En attente</span>
                        {% endif %}
                    {% else %}
                        <span class="status-pill status-todo">À faire</span>
                    {% endif %}
                </div>
                <p style="color: var(--text-dim); font-size: 0.9rem;">{{ d.get('consigne', 'Pas de consigne') }}...</p>

                {% if d.get('documents') %}
                <div style="margin-bottom: 10px;">
                    {% for did in d.documents %}
                        {% if did.startswith('carte_') and did in cartes %}
                            <a href="/cartes/voir/{{ did }}" class="doc-chip carte" target="_blank">🧠 {{ cartes[did].titre }}</a>
                        {% elif did in documents %}
                            <a href="/documents/voir/{{ did }}" class="doc-chip" target="_blank">📄 {{ documents[did].titre }}</a>
                        {% endif %}
                    {% endfor %}
                </div>
                {% endif %}
                
                {% if user in d.rendus and d.rendus[user].note %}
                    <a href="/devoirs/consulter/{{ did }}" class="btn btn-primary" style="width: 100%; margin-top: 20px;">Voir ma note ({{ d.rendus[user].note }}/20)</a>
                {% elif d.get('type') == 'code' %}
                    <a href="/devoirs/consulter/{{ did }}" class="btn btn-primary" style="width: 100%; margin-top: 20px;">
                        🐍 {{ 'Reprendre en attente de correction' if user in d.rendus else "Ouvrir l'exercice de code" }}
                    </a>
                {% else %}
                    <form action="/devoirs/rendre/{{ did }}" method="POST" style="margin-top: 20px;"
                          onsubmit="document.getElementById('rd-{{ did }}').value = document.getElementById('editor-rd-{{ did }}').innerHTML;">
                        <textarea name="reponse" placeholder="Écrivez votre réponse ou collez votre code ici (optionnel si vous joignez un document)..." style="height: 80px; margin-bottom: 10px;"></textarea>
                        <input type="hidden" name="reponse_doc" id="rd-{{ did }}">
                        <details style="margin-bottom: 15px;">
                            <summary style="cursor:pointer; color: var(--accent); font-size: 0.8rem; font-weight: 700; margin-bottom: 8px;">📎 Joindre un document mis en forme (optionnel)</summary>
                            {{ mini_editor("editor-rd-" ~ did)|safe }}
                        </details>
                        <button class="btn btn-outline" style="width: 100%;">Rendre le devoir</button>
                    </form>
                {% endif %}
            </div>
        {% endfor %}
    </div>
    {% elif page == 'cartes_eleve' %}
    <h1 style="font-size: 2.5rem; margin-bottom: 10px;">Cartes Mentales</h1>
    <p style="color: var(--text-dim); margin-bottom: 30px;">Explorez les cartes mentales préparées par votre formateur.</p>
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 22px;">
        {% for cid, c in cartes.items() %}
            <div class="carte-card">
                <div style="font-size: 2rem; margin-bottom: 10px;">🧠</div>
                <h3 style="margin: 0 0 8px 0;">{{ c.titre }}</h3>
                <p style="color: var(--text-dim); font-size: 0.8rem; margin-bottom: 20px;">{{ c.nodes|length }} nœuds</p>
                <a href="/cartes/voir/{{ cid }}" class="btn btn-outline" style="width: 100%;">Explorer</a>
            </div>
        {% else %}
            <p style="color: var(--text-dim);">Aucune carte mentale n'a encore été publiée.</p>
        {% endfor %}
    </div>

    {% elif page == 'carte_view' %}
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h1 style="font-size: 2rem; margin: 0;">🧠 {{ carte.titre }}</h1>
        <a href="{{ '/admin/cartes' if session.user == 'LearnCodePRO' else '/cartes' }}" class="btn btn-outline">← Retour</a>
    </div>
    <div class="glass-card" style="padding: 0; overflow: hidden;">
        <div class="carte-canvas-wrap" id="carte-canvas">
            <svg id="carte-svg" style="position:absolute; top:0; left:0; width:3000px; height:2000px; pointer-events:none;"></svg>
            <div id="nodes-layer" style="position:absolute; top:0; left:0; width:3000px; height:2000px;"></div>
        </div>
    </div>
    <script>
        window.carteNodes = {{ carte.nodes|tojson }};
        window.carteEdges = {{ carte.edges|tojson }};
        window.carteEditable = false;
        window.addEventListener('load', function(){ renderCarte(); });
    </script>

    {% elif page == 'admin_cartes_list' %}
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 30px;">
        <h1 style="margin:0;">🧠 Cartes Mentales</h1>
        <a href="/admin/cartes/new" class="btn btn-primary">+ Nouvelle carte</a>
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 22px;">
        {% for cid, c in cartes.items() %}
            <div class="carte-card">
                <h3 style="margin: 0 0 8px 0;">{{ c.titre }}</h3>
                <p style="color: var(--text-dim); font-size: 0.8rem; margin-bottom: 20px;">{{ c.nodes|length }} nœuds • {{ c.edges|length }} liens</p>
                <div style="display:flex; gap:10px;">
                    <a href="/admin/cartes/edit/{{ cid }}" class="btn btn-outline" style="flex:1;">Éditer</a>
                    <a href="/admin/cartes/delete/{{ cid }}" class="btn btn-outline" style="color:var(--danger); border-color:var(--danger);" onclick="return confirm('Supprimer cette carte ?')">🗑</a>
                </div>
            </div>
        {% else %}
            <p style="color: var(--text-dim);">Aucune carte pour le moment. Créez-en une !</p>
        {% endfor %}
    </div>

    {% elif page == 'carte_editor' %}
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <input id="carte-titre" value="{{ carte.titre }}" placeholder="Titre de la carte mentale" style="max-width: 420px; margin: 0;">
        <div class="carte-toolbar">
            <a href="/admin/cartes" class="btn btn-outline">← Retour</a>
            <button class="btn btn-outline" type="button" onclick="addNode()">+ Nœud</button>
            <button class="btn btn-primary" type="button" onclick="saveCarte()">💾 Enregistrer</button>
        </div>
    </div>
    <div class="glass-card" style="padding: 0; overflow: hidden;">
        <div class="carte-canvas-wrap" id="carte-canvas">
            <svg id="carte-svg" style="position:absolute; top:0; left:0; width:3000px; height:2000px; pointer-events:none;"></svg>
            <div id="nodes-layer" style="position:absolute; top:0; left:0; width:3000px; height:2000px;"></div>
        </div>
    </div>
    <p style="color: var(--text-dim); font-size: 0.8rem; margin-top: 15px;">🎨 change la couleur • 🔗 relie deux nœuds (cliquer sur le 1er puis le 2e) • 🗑 supprime le nœud. Glissez les nœuds pour les déplacer.</p>
    <script>
        window.carteId = "{{ carte_id or '' }}";
        window.carteNodes = {{ carte.nodes|tojson }};
        window.carteEdges = {{ carte.edges|tojson }};
        window.carteEditable = true;
        window.addEventListener('load', function(){ renderCarte(); });
    </script>

    {% elif page == 'admin_documents_list' %}
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 30px;">
        <h1 style="margin:0;">📄 Documents</h1>
        <a href="/admin/documents/new" class="btn btn-primary">+ Nouveau document</a>
    </div>
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 22px;">
        {% for did, d in documents.items() %}
            <div class="carte-card">
                <h3 style="margin: 0 0 8px 0;">{{ d.titre }}</h3>
                <p style="color: var(--text-dim); font-size: 0.8rem; margin-bottom: 20px;">Créé le {{ d.date }}</p>
                <div style="display:flex; gap:10px;">
                    <a href="/documents/voir/{{ did }}" class="btn btn-outline" style="flex:1;">Aperçu</a>
                    <a href="/admin/documents/edit/{{ did }}" class="btn btn-outline" style="flex:1;">Éditer</a>
                    <a href="/admin/documents/delete/{{ did }}" class="btn btn-outline" style="color:var(--danger); border-color:var(--danger);" onclick="return confirm('Supprimer ce document ?')">🗑</a>
                </div>
            </div>
        {% else %}
            <p style="color: var(--text-dim);">Aucun document pour le moment.</p>
        {% endfor %}
    </div>

    {% elif page == 'doc_editor' %}
    <form id="doc-form" action="/admin/documents/save" method="POST" onsubmit="document.getElementById('hidden-contenu').value = document.getElementById('editor-doc').innerHTML;">
        <input type="hidden" name="id" value="{{ doc_id or '' }}">
        <input type="hidden" name="contenu" id="hidden-contenu">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
            <input name="titre" value="{{ doc.titre }}" placeholder="Titre du document" required style="max-width: 420px; margin: 0;">
            <div style="display:flex; gap:10px;">
                <a href="/admin/documents" class="btn btn-outline">← Retour</a>
                <button type="submit" class="btn btn-primary">💾 Enregistrer</button>
            </div>
        </div>
        <div class="glass-card">
            {{ mini_editor("editor-doc", doc.contenu)|safe }}
        </div>
    </form>

    {% elif page == 'doc_view' %}
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
        <h1 style="font-size: 2rem; margin: 0;">📄 {{ doc.titre }}</h1>
        <a href="javascript:history.back()" class="btn btn-outline">← Retour</a>
    </div>
    <div class="doc-render">{{ doc.contenu|safe }}</div>

    {% elif page == 'admin_casier' %}
    <div class="glass-card" style="border-color: var(--primary); margin-bottom: 40px;">
    <h2>🆕 Créer un nouveau devoir</h2>
    <form action="/casier/nouveau" method="POST" style="margin-top:20px;">
        <input type="text" name="titre" placeholder="Titre du devoir (ex: Les boucles For)" required 
               class="btn" style="background:#000; text-align:left; border: 1px solid var(--border); width: 100%; margin-bottom: 15px;">
        
        <textarea name="consigne" placeholder="Énoncez ici la consigne détaillée du travail à faire..." 
                  style="width:100%; height:100px; background:#000; color:#fff; border:1px solid var(--border); border-radius:10px; padding:15px; margin-bottom: 15px;"></textarea>

        <p style="font-size: 0.75rem; color: var(--accent); text-transform: uppercase; font-weight: 800; margin-bottom: 10px;">🐍 Type de devoir</p>
        <div style="display:flex; gap: 15px; margin-bottom: 20px;">
            <label style="display:flex; align-items:center; gap:8px; background:#000; border:1px solid var(--border); border-radius:10px; padding:12px 18px; cursor:pointer; margin:0;">
                <input type="radio" name="type_devoir" value="texte" checked onchange="toggleDevoirType()" style="width:auto; margin:0;"> Texte / rendu libre
            </label>
            <label style="display:flex; align-items:center; gap:8px; background:#000; border:1px solid var(--border); border-radius:10px; padding:12px 18px; cursor:pointer; margin:0;">
                <input type="radio" name="type_devoir" value="code" onchange="toggleDevoirType()" style="width:auto; margin:0;"> Exercice de code Python (tests automatiques)
            </label>
        </div>

        <div id="code-devoir-zone" style="display:none; background:#000; border:1px solid var(--border); border-radius:12px; padding:20px; margin-bottom: 20px;">
            <label style="display:block; margin-bottom:8px; font-weight:700; color: var(--accent);">Code de départ donné à l'élève :</label>
            <textarea name="code_depart" placeholder="def addition(a, b):&#10;    # ton code ici&#10;    pass" 
                      style="width:100%; height:100px; background:#020203; color:#7dd3fc; border:1px solid var(--border); border-radius:10px; padding:15px; font-family:'Fira Code',monospace; margin-bottom: 20px;"></textarea>

            <label style="display:block; margin-bottom:8px; font-weight:700; color: var(--success);">Tests automatiques (exécutés après le code de l'élève) :</label>
            <div id="tests-box"></div>
            <button type="button" class="btn btn-outline" onclick="addTestCase()" style="width:100%; margin-top: 10px;">+ Ajouter un test</button>
        </div>

        <p style="font-size: 0.75rem; color: var(--accent); text-transform: uppercase; font-weight: 800; margin-bottom: 10px;">📎 Joindre des documents (optionnel)</p>
        <div style="display:flex; flex-wrap:wrap; gap: 10px; margin-bottom: 15px; background:#000; border:1px solid var(--border); border-radius:10px; padding:15px;">
            {% for did, d in documents.items() %}
                <label style="display:flex; align-items:center; gap:6px; background:rgba(99,102,241,0.08); padding:6px 12px; border-radius:20px; font-size:0.8rem; margin:0;">
                    <input type="checkbox" name="attach[]" value="{{ did }}" style="width:auto; margin:0;"> 📄 {{ d.titre }}
                </label>
            {% endfor %}
            {% for cid, c in cartes.items() %}
                <label style="display:flex; align-items:center; gap:6px; background:rgba(168,85,247,0.08); padding:6px 12px; border-radius:20px; font-size:0.8rem; margin:0;">
                    <input type="checkbox" name="attach[]" value="{{ cid }}" style="width:auto; margin:0;"> 🧠 {{ c.titre }}
                </label>
            {% endfor %}
            {% if not documents and not cartes %}
                <span style="color: var(--text-dim); font-size: 0.8rem;">Aucun document ni carte créé pour le moment.</span>
            {% endif %}
        </div>
        <div style="display:flex; gap:10px; margin-bottom: 20px;">
            <a href="/admin/documents/new" class="btn btn-outline" style="font-size:0.75rem; padding:8px 16px;">+ Nouveau document</a>
            <a href="/admin/cartes/new" class="btn btn-outline" style="font-size:0.75rem; padding:8px 16px;">+ Nouvelle carte</a>
        </div>
        
        <button type="submit" class="btn btn-primary" style="width: 100%;">Publier le devoir avec sa consigne</button>
    </form>
</div>

    <h2 style="margin-bottom: 20px;">📂 Copies à corriger</h2>
    {% for did, d in devoirs.items() %}
        <div class="glass-card" style="margin-bottom: 20px;">
            <h3 style="color: var(--primary);">{{ d.titre }}</h3>
            {% if d.get('documents') %}
            <div style="margin-bottom: 15px;">
                {% for did in d.documents %}
                    {% if did.startswith('carte_') and did in cartes %}
                        <a href="/cartes/voir/{{ did }}" class="doc-chip carte" target="_blank">🧠 {{ cartes[did].titre }}</a>
                    {% elif did in documents %}
                        <a href="/documents/voir/{{ did }}" class="doc-chip" target="_blank">📄 {{ documents[did].titre }}</a>
                    {% endif %}
                {% endfor %}
            </div>
            {% endif %}
            
            {% if not d.rendus %}
                <p style="color: var(--text-dim);">Aucun élève n'a encore rendu ce devoir.</p>
            {% endif %}

            {% for student, rendu in d.rendus.items() %}
    <div style="border: 1px solid var(--border); border-radius: 15px; margin-bottom: 15px; overflow: hidden; background: rgba(255,255,255,0.02);">
        
        <div onclick="const el = this.nextElementSibling; el.style.display = el.style.display === 'none' ? 'block' : 'none';" 
             style="cursor: pointer; padding: 15px 20px; display: flex; justify-content: space-between; align-items: center; background: rgba(255,255,255,0.03); hover: background: rgba(255,255,255,0.05);">
            <div style="display: flex; align-items: center; gap: 15px;">
                <span style="font-size: 1.2rem;">{% if rendu.note is not none %}✅{% else %}⏳{% endif %}</span>
                <b>👨‍🎓 {{ student }}</b>
                {% if rendu.note is not none %}
                    <span style="background: var(--success); color: #000; padding: 2px 8px; border-radius: 5px; font-size: 0.7rem; font-weight: bold;">{{ rendu.note }}/20</span>
                {% endif %}
            </div>
            <span style="color: var(--text-dim); font-size: 0.8rem;">Reçu le {{ rendu.date }} ▾</span>
        </div>

        <div style="display: none; padding: 20px; border-top: 1px solid var(--border);">
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                <div>
                    <p style="font-size: 0.7rem; color: var(--accent); text-transform: uppercase; margin-bottom: 5px;">Copie de l'élève :</p>
                    <div style="width: 100%;">
    <p style="font-size: 0.7rem; color: var(--accent); text-transform: uppercase; margin-bottom: 5px;">
        Copie de l'élève (Sélectible & Copiable) :
    </p>
    <textarea readonly id="copy-{{ student }}" 
              style="width:100%; height:150px; background:#000; color:#fff; border:1px solid #333; border-radius:10px; padding:15px; font-family:monospace; font-size:0.85rem; margin-bottom:10px;">{{ rendu.reponse }}</textarea>
    
    <button type="button" class="btn" style="font-size: 0.7rem; padding: 5px 10px;" 
            onclick="const txt = document.getElementById('copy-{{ student }}'); txt.select(); document.execCommand('copy');">
        📋 Copier la copie pour la corriger
    </button>
    {% if rendu.get('reponse_doc') %}
    <p style="font-size: 0.7rem; color: var(--secondary); text-transform: uppercase; margin: 15px 0 5px 0;">📎 Document joint par l'élève :</p>
    <div class="doc-render" style="max-height: 250px; overflow-y: auto; font-size: 0.85rem;">{{ rendu.reponse_doc|safe }}</div>
    {% endif %}
    {% if rendu.get('auto_results') %}
    <p style="font-size: 0.7rem; color: var(--accent); text-transform: uppercase; margin: 15px 0 5px 0;">🐍 Tests automatiques : {{ rendu.auto_score|int }}% de réussite</p>
    <div style="max-height: 220px; overflow-y: auto;">
        {% for r in rendu.auto_results %}
        <div style="padding:8px 12px; margin-bottom:6px; border-radius:8px; font-size:0.75rem;
            background:{{ 'rgba(16,185,129,0.08)' if r.passed else 'rgba(244,63,94,0.08)' }};
            border-left:3px solid {{ 'var(--success)' if r.passed else 'var(--danger)' }};">
            <b>{{ '✅' if r.passed else '❌' }} {{ r.nom }}</b><br>
            <span style="color:var(--text-dim);">Attendu : <code>{{ r.attendu }}</code> — Obtenu : <code>{{ r.obtenu }}</code></span>
        </div>
        {% endfor %}
    </div>
    {% endif %}
</div>
                </div>

                <form action="/admin/casier/noter" method="POST">
                    <input type="hidden" name="did" value="{{ did }}">
                    <input type="hidden" name="eleve" value="{{ student }}">
                    
                    <div style="display: flex; gap: 10px; margin-bottom: 10px;">
                        <input type="number" name="note" placeholder="Note" step="0.5" max="20" 
                               value="{{ rendu.note if rendu.note is not none else ((rendu.auto_score / 5) | round(1) if rendu.get('auto_score') is not none else '') }}" required 
                               style="width: 80px; background:#000; color:#fff; border:1px solid var(--border); border-radius:8px; padding:8px;">
                        <input type="text" name="feedback" placeholder="Commentaire..." value="{{ rendu.feedback or '' }}" 
                               style="flex-grow:1; background:#000; color:#fff; border:1px solid var(--border); border-radius:8px; padding:8px;">
                    </div>

                    <p style="font-size: 0.7rem; color: var(--success); text-transform: uppercase; margin-bottom: 5px;">Correction détaillée :</p>
                    <textarea name="correction" placeholder="Code corrigé..." 
                              style="width:100%; height:120px; background:#000; color:#7dd3fc; border:1px solid var(--border); border-radius:8px; padding:10px; font-family:monospace; font-size: 0.8rem;">{{ rendu.correction or '' }}</textarea>
                    
                    <button type="submit" class="btn btn-primary" style="width:100%; margin-top: 10px; padding: 8px;">Enregistrer</button>
                </form>
            </div>
        </div>
    </div>
{% endfor %} 
        </div>
    {% endfor %}
{% elif page == 'admin' %}
    <div class="glass-card">
        <h1>Gestion des modules</h1>
        <div style="display: grid; gap: 15px; margin-top: 20px;">
            {% for id_c, c in cours_dict.items() %}  <div class="glass-card" style="...">
                    <b>[{{ c.matiere }}]</b> {{ c.titre }}
                    <a href="/admin/edit/{{ id_c }}" class="btn">Modifier</a>
                </div>
            {% endfor %}
        </div>
    </div>
{% elif page == 'admin_list' %}
            <div class="glass-card">
                  <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 30px;">
                        <h2>Modules Disponibles</h2>
                        <a href="/admin/new" class="btn btn-primary">+ Nouveau</a>
                  </div>
                  {% for id, info in cours_dict.items() %}
                        <div class="rank-item">
                              <span><b>{{ info.titre }}</b> ({{id}})</span>
                              <div>
                                    <a href="/admin/edit/{{id}}" class="btn btn-outline" style="padding: 5px 15px;">Éditer</a>
                                    <a href="/admin/delete/{{id}}" class="btn btn-outline" style="color:var(--danger); border-color:var(--danger); padding: 5px 15px;">X</a>
                              </div>
                        </div>
                  {% endfor %}
            </div>

      {% elif page == 'projet' %}
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;">
                  <div>
                        <h1 style="font-size: 2.5rem; margin-bottom: 5px;">Sandbox Python</h1>
                        <p style="color: var(--text-dim);">Espace de développement libre. Votre code n'est pas sauvegardé à la fermeture.</p>
                  </div>
                  <button class="btn btn-primary" onclick="runSandbox()">
                        <span>▶</span> Exécuter le Projet
                  </button>
            </div>

            <div style="display: grid; grid-template-columns: 1fr; gap: 20px;">
                  <div class="glass-card" style="padding: 0; overflow: hidden; border: 1px solid var(--primary);">
                        <div style="background: rgba(99, 102, 241, 0.1); padding: 10px 25px; border-bottom: 1px solid var(--border); font-size: 0.8rem; font-weight: 800; color: var(--primary);">
                              MAIN.PY
                        </div>
                        <textarea id="sandbox-editor" style="margin: 0; border: none; height: 450px; font-family: 'Fira Code', monospace; background: #020203; color: #7dd3fc; padding: 25px; resize: none;" spellcheck="false"># Bienvenue dans la Sandbox
# Écrivez votre code Python librement ici

def salutation(nom):
      return f"Bonjour {nom}, prêt à coder ?"

print(salutation("Master"))
for i in range(5):
      print(f"Ligne de test n°{i+1}")
</textarea>
                  </div>
                  
                  <div class="glass-card">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                              <h3 style="margin: 0; font-size: 1rem;">Console de sortie</h3>
                              <button class="btn btn-outline" style="padding: 5px 15px; font-size: 0.7rem;" onclick="document.getElementById('sandbox-console').innerText = 'Console nettoyée.'">Effacer</button>
                              <button class="btn btn-outline" style="padding: 5px 15px; font-size: 0.7rem;" onclick="navigator.clipboard.writeText(document.getElementById('sandbox-editor').value)">Copier le code</button>
                        </div>
                        <div id="sandbox-console" style="background: #000; color: #fff; padding: 20px; border-radius: 16px; min-height: 150px; font-family: monospace; border-left: 4px solid var(--accent); white-space: pre-wrap;">Prêt pour l'exécution...</div>
                  </div>
            </div>
      {% elif page == 'cours' %}
           
<div class="card" style="padding: 0; border-radius: 20px; overflow: hidden; background: #0b0c10; border: 1px solid var(--border); min-height: 500px; display: flex; flex-direction: column;">
    
    <div id="slide-viewport" style="flex-grow: 1; padding: 60px; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; transition: all 0.5s ease;">
        <h1 id="slide-title" style="color: var(--primary); font-size: 2.5rem; margin-bottom: 20px; transform: translateY(0);">Chargement...</h1>
        <p id="slide-content" style="font-size: 1.2rem; line-height: 1.6; max-width: 800px; opacity: 0.9;"></p>
        
        <pre id="slide-code-container" style="display: none; background: #000; padding: 20px; border-radius: 10px; border: 1px solid #333; margin-top: 30px; text-align: left; width: 100%; max-width: 600px;">
            <code id="slide-code" style="color: #00ff00; font-family: 'Fira Code', monospace;"></code>
        </pre>
    </div>

    <div style="background: rgba(255,255,255,0.03); padding: 20px; display: flex; justify-content: space-between; align-items: center; border-top: 1px solid var(--border);">
        <button onclick="changeSlide(-1)" class="btn btn-outline" id="btn-prev">⬅ Précédent</button>
        
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="width: 200px; height: 6px; background: #222; border-radius: 10px; overflow: hidden;">
                <div id="slide-progress" style="width: 0%; height: 100%; background: var(--primary); transition: width 0.3s;"></div>
            </div>
            <span id="slide-number" style="font-family: monospace; font-size: 0.8rem; color: var(--text-dim);">1 / 1</span>
        </div>

        <button class="btn btn-primary" id="btn-next">Suivant ➡</button>
    </div>
</div>

<script>
    // On récupère les données depuis Python (transmises en JSON)
    const slides = {{ cours.slides|tojson if cours.slides else '[]' }};
    const cours_id = "{{ cours_id }}";
    let currentSlide = 0;

    function renderSlide() {
        if (slides.length === 0) return;

        const s = slides[currentSlide];
        const viewport = document.getElementById('slide-viewport');
        
        // Animation de sortie
        viewport.style.opacity = 0;
        viewport.style.transform = "translateX(-20px)";

        setTimeout(() => {
            // Mise à jour du contenu
            document.getElementById('slide-title').innerText = s.titre;
            document.getElementById('slide-content').innerText = s.contenu;
            
            // Gestion du code
            const codeBox = document.getElementById('slide-code-container');
            if (s.code) {
                codeBox.style.display = 'block';
                document.getElementById('slide-code').innerText = s.code;
            } else {
                codeBox.style.display = 'none';
            }

            // Mise à jour des infos
            document.getElementById('slide-number').innerText = `${currentSlide + 1} / ${slides.length}`;
            document.getElementById('slide-progress').style.width = `${((currentSlide + 1) / slides.length) * 100}%`;
            
            // Désactiver les boutons si besoin
            document.getElementById('btn-prev').disabled = (currentSlide === 0);
            document.getElementById('btn-next').innerText = (currentSlide === slides.length - 1) ? "Terminer" : "Suivant ➡";
if (currentSlide === slides.length - 1) {
    document.getElementById('btn-next').onclick = function() {
        window.location.href = '/quiz/' + cours_id + '/0';
    };
} else {
    document.getElementById('btn-next').onclick = function() {
        changeSlide(1);
    };
}

            // Animation d'entrée
            viewport.style.opacity = 1;
            viewport.style.transform = "translateX(0)";
        }, 300);
    }

function changeSlide(direction) {
    currentSlide += direction;
    if (currentSlide < 0) currentSlide = 0;
    renderSlide();
}
    // Initialisation
    window.onload = renderSlide;
</script>

      {% elif page == 'quiz' %}
            <div class="glass-card" id="quiz-container">
                  <div style="display: flex; justify-content: space-between; margin-bottom: 40px;">
                        <span style="font-weight: 800; color: var(--primary)">ÉVALUATION</span>
                        <span style="font-weight: 800;">{{ index + 1 }} SUR {{ total }}</span>
                  </div>
                  <h2 style="font-size: 2rem; line-height: 1.4; margin-bottom: 40px;">{{ exos.q }}</h2>

                  {% if exos.is_python %}
                        <textarea id="code-editor" spellcheck="false"># Codez ici...</textarea>
                        <div id="console">Console prête.</div>
                        <button class="btn btn-primary" style="width:100%; margin-top: 25px;" onclick="runTestPy('{{ exos.r }}')">Valider le Script</button>
                  {% elif exos.type == 'qcm' %}
                        <div style="display: flex; flex-direction: column; gap: 15px;">
                              {% for i, opt in enumerate_list(exos.opts) %}
                                    <button class="btn btn-outline" style="justify-content: flex-start; padding: 25px; border-radius: 20px;" onclick="checkAns({{ i }} == {{ exos.r }}, this)">
                                          <b style="color: var(--primary); margin-right: 15px;">{{ loop.index }}.</b> {{ opt }}
                                    </button>
                              {% endfor %}
                        </div>
                  {% else %}
                        <input type="text" id="ans-text" placeholder="Réponse attendue..." autocomplete="off">
                        <button class="btn btn-primary" style="width:100%;" onclick="checkAns(document.getElementById('ans-text').value.toLowerCase().trim() == '{{ exos.r }}'.toLowerCase().trim())">Vérifier</button>
                  {% endif %}
            </div>
        {% elif page == 'resultat' %}
            <div class="glass-card" style="text-align: center; padding: 60px 40px;">
                  <div style="font-size: 5rem; margin-bottom: 20px;">
                        {% if score >= 80 %} 🎉 {% elif score >= 50 %} 😎 {% else %} 📚 {% endif %}
                        
                  </div>
                  <h1 style="font-size: 2.5rem; margin-bottom: 10px;">Résultat du module</h1>
                  <p style="color: var(--primary); font-weight: 800; text-transform: uppercase; letter-spacing: 2px;">{{ cours.titre }}</p>
                  
                  <div style="margin: 40px 0;">
                        <div style="font-size: 4rem; font-weight: 900; color: #fff;">{{ score }}%</div>
                        <div class="progress-bar" style="max-width: 400px; margin: 20px auto; height: 15px;">
                              <div class="progress-fill" style="width: {{ score }}%; background: linear-gradient(90deg, var(--primary), var(--accent));"></div>
                        </div>
                  </div>

                  <p style="font-size: 1.2rem; color: var(--text-dim); max-width: 600px; margin: 0 auto 40px auto; line-height: 1.6;">
                        {{ message }}
                  </p>

                  <div style="display: flex; gap: 20px; justify-content: center;">
                        <a href="/cours/{{ cours_id }}" class="btn btn-outline">Recommencer</a>
                        <a href="/dashboard" class="btn btn-primary">Retour aux modules</a>
                        <a href="/stats" class="btn btn-outline" style="border-color: var(--accent); color: var(--accent);">Voir mes stats</a>
                  </div>
            </div>
            
        {% elif page == 'voir_devoir' %}
    {# --- BLOC ANIMATION LEVEL UP (Version sécurisée) --- #}
    {% if USERS[user].get('pending_level_up') %}
        {% set user_xp = USERS[user].get('xp', 0) %}
        <div id="level-up-overlay" style="display: flex;">
            <p style="color: var(--primary); font-weight: 800; letter-spacing: 5px;">NOUVEAU RANG ATTEINT</p>
            <h1 class="lvl-text">LEVEL UP !</h1>
            <p id="new-lvl-nb" style="font-size: 2rem; font-weight: 800; color: #fff;">
                NIVEAU {{ (user_xp // 100) + 1 }}
            </p>
            <button class="btn btn-primary" style="margin-top: 30px;" onclick="closeLevelUpDevoir()">CONTINUER</button>
        </div>
        
        <script>
        function closeLevelUpDevoir() {
            document.getElementById('level-up-overlay').style.display = 'none';
            fetch('/clear_level_up');
        }
        if (typeof confetti === 'function') {
            confetti({ particleCount: 150, spread: 70, origin: { y: 0.6 } });
        }
        </script>
    {% endif %}
        
    <div class="glass-card" style="max-width: 1400px; margin: 0 auto;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 30px;">
            <div>
                <h1 style="margin: 0; font-size: 1.8rem;">Analyse du Devoir</h1>
                <p style="color: var(--text-dim); margin: 5px 0 0 0;">{{ devoir.titre }}</p>
                {% if devoir.get('documents') %}
                <div style="margin-top: 12px;">
                    {% for did in devoir.documents %}
                        {% if did.startswith('carte_') and did in CARTES %}
                            <a href="/cartes/voir/{{ did }}" class="doc-chip carte" target="_blank">🧠 {{ CARTES[did].titre }}</a>
                        {% elif did in DOCUMENTS %}
                            <a href="/documents/voir/{{ did }}" class="doc-chip" target="_blank">📄 {{ DOCUMENTS[did].titre }}</a>
                        {% endif %}
                    {% endfor %}
                </div>
                {% endif %}
            </div>
            <a href="/devoirs" class="btn btn-outline" style="border-radius: 12px;">← Retour au casier</a>
        </div>

        {% set rendu = devoir.rendus.get(user) %}

        {% if rendu and rendu.note is not none %}
            {# --- CAS 1 : LE DEVOIR EST RENDU ET NOTÉ (Affichage de la correction) --- #}
            <div style="display: flex; align-items: center; background: rgba(255,255,255,0.03); border: 1px solid var(--border); border-radius: 24px; padding: 25px; gap: 40px; margin-bottom: 40px; box-shadow: 0 10px 30px rgba(0,0,0,0.2);">
                <div style="text-align: center; border-right: 1px solid var(--border); padding-right: 40px; min-width: 120px;">
                    <p style="font-size: 0.7rem; text-transform: uppercase; color: var(--primary); font-weight: 800; letter-spacing: 1px; margin-bottom: 5px;">Note Finale</p>
                    <div style="font-size: 2.8rem; font-weight: 900; line-height: 1; position: relative; display: inline-block;">
                        {{ rendu.note }}<span style="font-size: 1.2rem; opacity: 0.4;">/20</span>
                        <div style="position: absolute; top: -15px; right: -30px; background: var(--accent); color: #000; font-size: 0.6rem; padding: 2px 6px; border-radius: 6px; font-weight: bold; box-shadow: 0 4px 10px rgba(0,0,0,0.3);">
                            +{{ (rendu.note|float * 5)|int }} XP
                        </div>
                    </div>
                </div>

                <div style="flex-grow: 1;">
                    <p style="font-size: 0.7rem; text-transform: uppercase; color: var(--accent); font-weight: 800; letter-spacing: 1px; margin-bottom: 8px;">Commentaire du formateur</p>
                    <p style="margin: 0; font-style: italic; color: var(--text-dim); line-height: 1.5; font-size: 1.05rem;">
                        "{{ rendu.feedback or "Travail bien reçu et analysé." }}"
                    </p>
                </div>

                <div style="display: flex; flex-direction: column; align-items: flex-end; padding-left: 30px; border-left: 1px solid var(--border);">
                    <div style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid #10b981; padding: 6px 16px; border-radius: 10px; font-weight: 800; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1px;">
                        ✅ Corrigé
                    </div>
                    <span style="font-size: 0.65rem; color: var(--text-dim); margin-top: 8px; font-weight: 600;">Session : 2025-2026</span>
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1.5fr; gap: 35px; align-items: start;">
                <div style="position: sticky; top: 20px;">
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                        <span style="background: var(--border); padding: 4px 8px; border-radius: 6px; font-size: 0.7rem;">TON RENDU</span>
                        <p style="font-size: 0.85rem; font-weight: bold; margin: 0; opacity: 0.8;">Posté le {{ rendu.date }}</p>
                    </div>
                    <pre style="background: #000; padding: 25px; border-radius: 20px; border: 1px solid var(--border); font-size: 0.9rem; color: #888; white-space: pre-wrap; font-family: 'Fira Code', monospace; line-height: 1.6; margin: 0; box-shadow: inset 0 2px 10px rgba(0,0,0,0.5);">{{ rendu.reponse }}</pre>
                    {% if rendu.get('auto_score') is not none %}
                    <p style="font-size: 0.7rem; color: var(--accent); text-transform: uppercase; margin: 15px 0 5px 0;">🐍 Tests automatiques (à ton dernier essai) : {{ rendu.auto_score|int }}%</p>
                    {% endif %}
                    {% if rendu.get('reponse_doc') %}
                    <p style="font-size: 0.7rem; color: var(--secondary); text-transform: uppercase; margin: 15px 0 5px 0;">📎 Document joint :</p>
                    <div class="doc-render" style="font-size: 0.85rem;">{{ rendu.reponse_doc|safe }}</div>
                    {% endif %}
                </div>
                
                <div>
                    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 15px;">
                        <span style="background: var(--success); color: #000; padding: 4px 8px; border-radius: 6px; font-size: 0.7rem; font-weight: bold;">CORRECTION</span>
                        <p style="font-size: 0.85rem; font-weight: bold; margin: 0; color: var(--success);">Analyse détaillée :</p>
                    </div>
                    <div id="zone-correction" class="correction-text" 
                         style="background: rgba(16, 185, 129, 0.04); padding: 30px; border-radius: 25px; border: 1px solid var(--success); font-size: 1rem; color: #fff; white-space: pre-wrap; font-family: 'Fira Code', monospace; line-height: 1.7; min-height: 200px; box-shadow: 0 15px 35px rgba(0,0,0,0.3);">{{ rendu.correction or "Pas de correction détaillée." }}</div>
                </div>
            </div>

        {% elif rendu %}
            {# --- CAS 2 : RENDU MAIS PAS ENCORE NOTÉ --- #}
            <div style="text-align: center; padding: 60px; background: rgba(255,255,255,0.02); border-radius: 30px; border: 1px dashed var(--border);">
                <div style="font-size: 4rem; margin-bottom: 20px;">⌛</div>
                <h2 style="color: var(--primary);">Devoir en cours de correction</h2>
                <p style="color: var(--text-dim); max-width: 500px; margin: 0 auto 30px auto;">
                    Ton travail a bien été envoyé le <b>{{ rendu.date }}</b>. Reviens plus tard pour consulter ta note et le feedback du formateur.
                </p>
                <div style="background: #000; padding: 20px; border-radius: 15px; text-align: left; max-width: 600px; margin: 0 auto; opacity: 0.6;">
                    <small style="color: var(--primary);">Rappel de ton message :</small>
                    <p style="margin-top: 10px; font-family: monospace; white-space: pre-wrap;">{{ rendu.reponse }}</p>
                    {% if rendu.get('auto_score') is not none %}
                    <p style="margin-top: 10px; color: var(--accent); font-size: 0.8rem;">🐍 Score aux tests automatiques : {{ rendu.auto_score|int }}%</p>
                    {% endif %}
                </div>
            </div>

        {% else %}
            {# --- CAS 3 : PAS ENCORE RENDU (Affichage du formulaire) --- #}
            {% if devoir.get('type') == 'code' %}
            {# --- FORMULAIRE POUR UN DEVOIR DE CODE : ÉDITEUR + TESTS AUTOMATIQUES --- #}
            <div style="max-width: 900px; margin: 0 auto;">
                <div style="background: var(--success); color: #000; padding: 20px; border-radius: 20px 20px 0 0; font-weight: bold;">
                    🐍 Exercice de code Python
                </div>
                <form action="/devoirs/rendre/{{ id_d }}" method="POST" style="background: rgba(255,255,255,0.03); padding: 30px; border: 1px solid var(--border); border-radius: 0 0 20px 20px;"
                      onsubmit="document.getElementById('reponse-code-{{ id_d }}').value = document.getElementById('code-editor-{{ id_d }}').value;">
                    <input type="hidden" name="reponse" id="reponse-code-{{ id_d }}">
                    <input type="hidden" name="auto_score" id="auto-score-{{ id_d }}" value="0">
                    <input type="hidden" name="auto_results" id="auto-results-{{ id_d }}" value="[]">

                    <label style="display: block; margin-bottom: 10px; font-weight: bold;">Ton code :</label>
                    <textarea id="code-editor-{{ id_d }}" spellcheck="false"
                        style="width: 100%; min-height: 260px; background: #020203; border: 1px solid var(--border); border-radius: 15px; color: #7dd3fc; padding: 20px; font-family: 'Fira Code', monospace; line-height: 1.6;">{{ devoir.get('code_depart', '') }}</textarea>

                    <button type="button" class="btn btn-outline" style="width: 100%; margin-top: 15px;" onclick="runDevoirTests('{{ id_d }}')">▶ Lancer les tests</button>

                    <div id="test-results-{{ id_d }}" style="margin-top: 20px;">
                        <p style="color: var(--text-dim); font-size: 0.85rem;">Lance les tests avant de rendre pour vérifier ton code.</p>
                    </div>

                    <button type="submit" class="btn btn-primary" style="width: 100%; padding: 18px; font-size: 1.1rem; margin-top: 20px;">
                        Envoyer le devoir au formateur
                    </button>
                </form>
            </div>
            <script>
                window['tests_{{ id_d }}'] = {{ devoir.get('tests', [])|tojson }};
            </script>
            {% else %}
            <div style="max-width: 800px; margin: 0 auto;">
                <div style="background: var(--primary); color: #000; padding: 20px; border-radius: 20px 20px 0 0; font-weight: bold;">
                    📝 Formulaire de rendu
                </div>
                <form action="/devoirs/rendre/{{ id_d }}" method="POST" style="background: rgba(255,255,255,0.03); padding: 30px; border: 1px solid var(--border); border-radius: 0 0 20px 20px;"
                      onsubmit="document.getElementById('rd-full-{{ id_d }}').value = document.getElementById('editor-rd-full-{{ id_d }}').innerHTML;">
                    <div style="margin-bottom: 25px;">
                        <label style="display: block; margin-bottom: 10px; font-weight: bold;">Ton travail / Explications :</label>
                        <textarea name="reponse" placeholder="Colle ton code ou tes explications ici..." 
                            style="width: 100%; min-height: 200px; background: #000; border: 1px solid var(--border); border-radius: 15px; color: #fff; padding: 20px; font-family: 'Fira Code', monospace;"></textarea>
                    </div>
                    <input type="hidden" name="reponse_doc" id="rd-full-{{ id_d }}">
                    <div style="margin-bottom: 25px;">
                        <label style="display: block; margin-bottom: 10px; font-weight: bold;">📎 Document mis en forme (optionnel) :</label>
                        {{ mini_editor("editor-rd-full-" ~ id_d)|safe }}
                    </div>
                    <button type="submit" class="btn btn-primary" style="width: 100%; padding: 18px; font-size: 1.1rem;">
                        Envoyer le devoir au formateur
                    </button>
                </form>
            </div>
            {% endif %}
        {% endif %}
    </div>

      {% elif page == 'stats' %}
<div style="display: grid; grid-template-columns: 1.6fr 1fr; gap: 30px;">
    <div class="glass-card">
        <h2 style="margin-bottom: 30px;">Analyse par Module</h2>
        <canvas id="histoChart" style="max-height: 350px;"></canvas>
        
        <script>
            window.addEventListener('load', () => {
                const canvas = document.getElementById('histoChart');
                if (canvas) {
                    const ctx = canvas.getContext('2d');
                    new Chart(ctx, {
                        type: 'bar',
                        data: {
                            labels: {{ chart_labels|tojson }},
                            datasets: [{
                                label: 'Performance (%)',
                                data: {{ chart_data|tojson }},
                                backgroundColor: 'rgba(99, 102, 241, 0.6)',
                                borderColor: '#6366f1',
                                borderWidth: 2,
                                borderRadius: 10
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            scales: {
                                y: { beginAtZero: true, max: 100, grid: { color: 'rgba(255,255,255,0.05)' } },
                                x: { grid: { display: false } }
                            },
                            plugins: { legend: { display: false } }
                        }
                    });
                }
            });
        </script>
    </div>

    <div class="glass-card" style="text-align: center;">
        <h2 style="margin-bottom: 30px;">Votre Rang</h2>
        <div style="font-size: 5rem; font-weight: 800; color: var(--primary); line-height: 1;">{{ grade }}</div>
        <p style="color: var(--text-dim); text-transform: uppercase; font-weight: 700; margin-top: 15px;">Classement Actuel</p>
        
        <div style="margin-top: 40px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div class="glass-card" style="margin: 0; padding: 20px;">
                <div style="font-size: 1.3rem; font-weight: 800;">{{ score }}</div>
                <div style="font-size: 0.7rem; color: var(--text-dim);">XP ACCUMULÉE</div>
            </div>
            <div class="glass-card" style="margin: 0; padding: 20px;">
                <div style="font-size: 1.3rem; font-weight: 800;">{{ moyenne }}%</div>
                <div style="font-size: 0.7rem; color: var(--text-dim);">PRÉCISION MOY.</div>
            </div>
        </div>
    </div>
</div>

<div class="glass-card" style="margin-top: 30px;">
    <h2 style="margin-bottom: 20px;">Mes Succès ({{ badges|length }})</h2>
    <div class="badge-grid">
        {% for b in badges %}
        <div class="badge-card">
            <span class="badge-icon">{{ b.i }}</span>
            <span class="badge-name" style="color: {{ b.c }}">{{ b.n }}</span>
            <span class="badge-desc">{{ b.d }}</span>
            <!-- La barre de couleur en bas comme sur la V1 -->
            <div style="width: 40px; height: 3px; background: {{ b.c }}; margin-top: 15px; border-radius: 2px;"></div>
        </div>
        {% else %}
        <p style="color: var(--text-dim); font-size: 0.9rem;">Continuez à apprendre pour débloquer des badges !</p>
        {% endfor %}
    </div>
</div>
</div>

<div class="glass-card" style="margin-top: 30px;">
    <h2 style="margin-bottom: 20px;">Leaderboard Global</h2>
    <div style="margin-top: 10px;">
        {% for p in leaderboard %}
        <div class="rank-item {{ 'active' if p.name == session.user else '' }}">
            <div style="display: flex; gap: 25px; align-items: center;">
                <span style="font-weight: 800; font-size: 1.3rem; width: 30px;">#{{ loop.index }}</span>
                <b>{{ p.name }}</b>
            </div>
            <div style="text-align: right;">
                <span style="font-weight: 800; color: var(--primary);">{{ p.score }} XP</span>
                <div style="font-size: 0.7rem; color: var(--text-dim);">{{ p.courses }} cours validés</div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
      
        {% elif page == 'admin_edit' %}
<div class="glass-card">
    <h1 style="margin-bottom: 30px;">Configuration du Module</h1>
    
    <form action="/admin/save" method="post">
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom:20px;">
            <input name="matiere" placeholder="Catégorie" value="{{ cours_to_edit.matiere if edit_mode else '' }}" required>
            <input name="id" placeholder="ID (ex: intro_python)" value="{{ edit_id if edit_mode else '' }}" required>
        </div>
        <input name="titre" placeholder="Titre du module" value="{{ cours_to_edit.titre if edit_mode else '' }}" required>
        <label>Contenu du cours (Texte classique) :</label>
        <textarea name="contenu" id="admin-area" rows="10" style="margin-top:10px; margin-bottom:30px;">{{ cours_to_edit.contenu if edit_mode else '' }}</textarea>

        <h3 style="color: var(--primary);">1. Mode Slides</h3>
        <div id="slides-box">
            {% if edit_mode and cours_to_edit.slides %}
                {% for s in cours_to_edit.slides %}
                <div class="glass-card" style="background: rgba(255,255,255,0.02); margin-bottom: 10px; padding: 15px;">
                    <div style="display: flex; justify-content: space-between;">
                        <b>SLIDE</b>
                        <button type="button" onclick="this.parentElement.parentElement.remove()" style="color:red; background:none; border:none; cursor:pointer;">[X]</button>
                    </div>
                    <input name="slide_titre[]" value="{{ s.titre }}" placeholder="Titre slide" style="margin: 5px 0;">
                    <textarea name="slide_contenu[]" placeholder="Contenu">{{ s.contenu }}</textarea>
                    <input name="slide_code[]" value="{{ s.code }}" placeholder="Code Python" style="font-family:monospace; color:#0f0;">
                </div>
                {% endfor %}
            {% endif %}
        </div>
        <button type="button" class="btn btn-outline" onclick="addSlide()" style="width:100%; margin-bottom: 30px;">+ Ajouter une Slide</button>

        <h3 style="color: var(--primary);">2. Quiz & Exercices</h3>
        <div id="q-box" style="margin-top: 20px;">
            {% if edit_mode and cours_to_edit.exercices %}
                {% for idx_q, ex in enumerate_list(cours_to_edit.exercices) %}
                <div class="glass-card" style="background: #000; margin-bottom: 15px; padding: 15px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <select name="type[]">
                            <option value="text" {{'selected' if ex.type=='text'}}>Saisie Libre</option>
                            <option value="qcm" {{'selected' if ex.type=='qcm'}}>QCM</option>
                        </select>
                        <button type="button" onclick="this.parentElement.parentElement.remove()" style="color:red; background:none; border:none; cursor:pointer;">[X]</button>
                    </div>
                    
                    <input name="q[]" value="{{ex.q}}" placeholder="Question" style="margin-bottom:10px;">
                    <input name="opts[]" value="{{ex.opts|join(',') if ex.opts else ''}}" placeholder="Options (si QCM)">
                    
                    <input name="r[]" value="{{ex.r}}" placeholder="Réponse correcte" style="margin-top:10px;">
                    <label style="display:block; margin-top:10px;">
                        <input type="checkbox" name="is_py[]" value="{{idx_q}}" {{'checked' if ex.is_python}}> Exercice Python
                    </label>
                </div>
                {% endfor %}
            {% endif %}
        </div>
        <button type="button" class="btn btn-outline" onclick="addQ()" style="width:100%; margin-bottom: 30px;">+ Ajouter une Question</button>

        <button type="submit" class="btn btn-primary" style="width:100%; padding: 20px; font-weight: bold; margin-top: 20px;">
            💾 SAUVEGARDER LES MODIFICATIONS
        </button>
    </form>
</div>
{% elif page == 'login' %}
            <div class="glass-card" style="max-width: 450px; margin: 100px auto; text-align: center; padding: 50px;">
                  <h1 style="font-size: 2.5rem; margin-bottom: 10px;">Accès LEARNCODE</h1>
                  <form action="/login" method="post">
                        <input name="username" placeholder="Pseudo" required style="text-align: center;">
                        <button class="btn btn-primary" style="width: 100%;">Commencer</button>
                  </form>
            </div>
      {% endif %}
</div>


<script>
    // 1. MOTEUR GENIALLY
    function parseGenially() {
        const zone = document.getElementById('moteur-genially');
        if(!zone) return;
        let html = zone.innerHTML;
        html = html.replace(/\[REVELER:(.*?)\]/g, '<div class="gen-reveal" onclick="this.innerHTML=\'$1\';this.style.background=\'none\';this.style.border=\'none\'">👁 CLIQUEZ POUR RÉVÉLER</div>');
        html = html.replace(/\[FLOU:(.*?)\]/g, '<span class="gen-blur" onclick="this.classList.toggle(\'gen-blur\')">$1</span>');
        html = html.replace(/\[DEFINITION:(.*?):(.*?)\]/g, '<span class="gen-hotspot" data-content="$2">$1</span>');
        html = html.replace(/\[ASTUCE:(.*?)\]/g, '<div class="gen-tip"><b>💡 ASTUCE :</b> $1</div>');
        html = html.replace(/\[ALERTE:(.*?)\]/g, '<div class="gen-alert"><b>⚠️ ATTENTION :</b> $1</div>');
        html = html.replace(/\[TOUCHE:(.*?)\]/g, '<span class="gen-kbd">$1</span>');
        zone.innerHTML = html;
    }

    // 2. INITIALISATION PYTHON
    let py;
    async function startPy() {
        try { py = await loadPyodide(); console.log("Python prêt !"); } 
        catch(e) { console.error("Erreur Pyodide:", e); }
    }

    window.addEventListener('DOMContentLoaded', () => {
        parseGenially();
        startPy();
    });

    // 3. SYSTÈME DE QUIZ ET SCORES
    function sendScore(final) {
        fetch('/update_score', {
            method:'POST', 
            headers:{'Content-Type':'application/json'}, 
            body:JSON.stringify({id:'{{cours_id}}', score:final})
        })
        .then(res => res.json())
        .then(data => {
            if (data.level_up) {
                confetti({ particleCount: 200, spread: 80, origin: { y: 0.6 } });
                document.getElementById('new-lvl-nb').innerText = "Niveau " + data.new_level;
                document.getElementById('level-up-overlay').style.display = 'flex';
                
                // Redirection après le clic sur le bouton de l'overlay
                document.querySelector('#level-up-overlay .btn').onclick = () => {
                    window.location.href = "/resultat/{{ cours_id }}/" + final;
                };
            } else {
                // Redirection directe vers la page résultat
                window.location.href = "/resultat/{{ cours_id }}/" + final;
            }
        });
    }
    function appliquerColoration() {
    const zone = document.getElementById('zone-correction');
    if (zone) {
        let texte = zone.innerHTML;
        
        // On remplace TOUTE la balise [R]...[/R] par le span rouge
        // Le texte entre les balises est capturé par (.*?) et replacé par $1
        texte = texte.replace(/\[R\](.*?)\[\/R\]/g, '<span style="color: #ff4d4d; font-weight: bold; background: rgba(255,0,0,0.1); padding: 2px 4px; border-radius: 4px;">$1</span>');
        
        // Optionnel : Vert pour [V] et Orange pour [O]
        texte = texte.replace(/\[V\](.*?)\[\/V\]/g, '<span style="color: #2ecc71; font-weight: bold;">$1</span>');
        texte = texte.replace(/\[O\](.*?)\[\/O\]/g, '<span style="color: #f39c12; font-weight: bold;">$1</span>');

        // On réinjecte le résultat final dans la zone
        zone.innerHTML = texte;
    }
}

// On lance la fonction dès que la page est prête
window.addEventListener('load', appliquerColoration);
    function checkAns(isOk, btn = null) {
        let sc = parseInt(sessionStorage.getItem("master_score") || "0");
        {% if index is defined and index == 0 %} sc = 0; {% endif %}
        
        if(isOk) sc++;
        sessionStorage.setItem("master_score", sc);
        
        const container = document.getElementById('quiz-container');
        if(container) container.style.borderColor = isOk ? 'var(--success)' : 'var(--danger)';
        if(btn) btn.style.background = isOk ? 'var(--success)' : 'var(--danger)';

        setTimeout(() => {
            {% if index is defined and index + 1 < total %}
                window.location.href = "/quiz/{{ cours_id }}/{{index + 1}}";
            {% elif index is defined %}
                let finalScore = Math.round((sc / {{total}}) * 100);
                if (finalScore === 100) {
                    confetti({ particleCount: 150, spread: 70, origin: { y: 0.6 } });
                    setTimeout(() => { sendScore(finalScore); }, 1500);
                } else {
                    sendScore(finalScore);
                }
            {% endif %}
        }, 800);
    }
    function parseCorrection() {
    const zones = document.querySelectorAll('.correction-text');
    zones.forEach(zone => {
        let content = zone.innerHTML;
        
        // Cette version remplace TOUTE la balise [R]texte[/R] par le span
        // Le "$1" représente uniquement ce qui est entre les deux balises
        content = content.replace(/\[R\]([\s\S]*?)\[\/R\]/g, '<span style="color: #ff4d4d; font-weight: bold; background: rgba(255,0,0,0.1); padding: 2px 4px; border-radius: 4px;">$1</span>');
        // Pour le Vert [V]texte[/V]
content = content.replace(/\[V\]([\s\S]*?)\[\/V\]/g, '<span style="color: #2ecc71; font-weight: bold;">$1</span>');

// Pour l'Orange [O]texte[/O]
content = content.replace(/\[O\]([\s\S]*?)\[\/O\]/g, '<span style="color: #f39c12; font-weight: bold;">$1</span>');
        
        zone.innerHTML = content;
    });
}

// On s'assure qu'il s'exécute bien une fois que la page est chargée
window.addEventListener('load', parseCorrection);
    // 4. AUTRES FONCTIONS (Sandbox, Admin)
    async function runSandbox() {
        const out = document.getElementById('sandbox-console');
        const code = document.getElementById('sandbox-editor').value;
        if (!py) { out.innerText = "Chargement..."; return; }
        await py.runPythonAsync("import sys, io\nsys.stdout = io.StringIO()");
        try {
            await py.runPythonAsync(code);
            out.innerText = (await py.runPythonAsync("sys.stdout.getvalue()")).trim() || "Terminé.";
        } catch(e) { out.innerText = "ERREUR :\n" + e; }
    }

    async function runTestPy(val) {
        const out = document.getElementById('console'); 
        if (!py) return;
        await py.runPythonAsync("import sys, io\nsys.stdout = io.StringIO()");
        try {
            await py.runPythonAsync(document.getElementById('code-editor').value);
            const res = (await py.runPythonAsync("sys.stdout.getvalue()")).trim();
            out.innerText = res; checkAns(res.toLowerCase() == val.toLowerCase());
        } catch(e) { out.innerText = e; checkAns(false); }
    }
    // Fonction pour mettre le Genially en plein écran (Mode PowerPoint)
function goFullScreen() {
    const elem = document.getElementById("container-genially");
    if (elem.requestFullscreen) {
        elem.requestFullscreen();
    } else if (elem.webkitRequestFullscreen) { /* Safari */
        elem.webkitRequestFullscreen();
    }
}
// --- SECTION ADMIN ---

function ins(t) { 
    const a = document.getElementById('admin-area'); 
    if(a) { a.value += t; a.focus(); }
}

function addSlide() {
    var box = document.getElementById('slides-box');
    if(!box) return;
    var div = document.createElement('div');
    div.className = "glass-card";
    div.style.marginBottom = "15px";
    div.innerHTML = '<div style="display:flex;justify-content:space-between"><b>SLIDE</b><button type="button" onclick="this.parentElement.parentElement.remove()" style="color:red;background:none;border:none;cursor:pointer">X</button></div>' +
                    '<input name="slide_titre[]" placeholder="Titre" style="width:100%;margin:5px 0">' +
                    '<textarea name="slide_contenu[]" placeholder="Texte" style="width:100%;height:60px;background:#000;color:#fff"></textarea>' +
                    '<input name="slide_code[]" placeholder="Code Python" style="width:100%;color:#0f0;background:#000">';
    box.appendChild(div);
}

function addQ() {
    var box = document.getElementById('q-box');
    if(!box) return;
    var i = box.children.length;
    var d = document.createElement('div');
    d.className = 'glass-card'; d.style.background = '#000';
    d.innerHTML = '<select name="type[]"><option value="text">Saisie</option><option value="qcm">QCM</option></select>' +
                  '<input name="q[]" placeholder="Question" style="width:100%">' +
                  '<input name="opts[]" placeholder="Options" style="width:100%">' +
                  '<input name="r[]" placeholder="Réponse" style="width:100%">' +
                  '<label><input type="checkbox" name="is_py[]" value="' + i + '"> Python</label>';
    box.appendChild(d);
}

// --- DEVOIRS DE CODE : CONSTRUCTEUR DE TESTS AUTOMATIQUES ---
function toggleDevoirType() {
    const isCode = document.querySelector('input[name="type_devoir"]:checked').value === 'code';
    const zone = document.getElementById('code-devoir-zone');
    if (!zone) return;
    zone.style.display = isCode ? 'block' : 'none';
    if (isCode && document.getElementById('tests-box').children.length === 0) {
        addTestCase();
    }
}

function addTestCase() {
    const box = document.getElementById('tests-box');
    if (!box) return;
    const div = document.createElement('div');
    div.className = 'glass-card';
    div.style.cssText = 'background:rgba(255,255,255,0.02); margin-bottom:10px; padding:15px;';
    div.innerHTML = `
        <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
            <b style="font-size:0.8rem; color:var(--success);">TEST</b>
            <button type="button" onclick="this.closest('.glass-card').remove()" style="color:var(--danger); background:none; border:none; cursor:pointer;">✕</button>
        </div>
        <input name="test_nom[]" placeholder="Nom du test (ex: Addition simple)" style="margin-bottom:8px;">
        <textarea name="test_harnais[]" placeholder="Code exécuté après celui de l'élève (ex: print(addition(2,3)))" 
                  style="width:100%; height:60px; background:#020203; color:#7dd3fc; border:1px solid var(--border); border-radius:8px; padding:10px; font-family:'Fira Code',monospace; font-size:0.85rem; margin-bottom:8px;"></textarea>
        <input name="test_attendu[]" placeholder="Sortie attendue (ex: 5)" style="font-family:'Fira Code',monospace;">
    `;
    box.appendChild(div);
}

// --- CARTES MENTALES : MOTEUR ---
const CARTE_COLORS = ['#6366f1','#a855f7','#22d3ee','#10b981','#f43f5e','#fbbf24'];
let carteLinkFrom = null;

function renderCarte() {
    const layer = document.getElementById('nodes-layer');
    const svg = document.getElementById('carte-svg');
    if (!layer || !svg) return;
    layer.innerHTML = '';
    svg.innerHTML = '';

    (window.carteEdges || []).forEach(e => {
        const from = window.carteNodes.find(n => n.id === e.from);
        const to = window.carteNodes.find(n => n.id === e.to);
        if (!from || !to) return;
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', from.x + 70); line.setAttribute('y1', from.y + 25);
        line.setAttribute('x2', to.x + 70); line.setAttribute('y2', to.y + 25);
        line.setAttribute('stroke', '#6366f1'); line.setAttribute('stroke-width', '2'); line.setAttribute('opacity', '0.6');
        svg.appendChild(line);
    });

    (window.carteNodes || []).forEach(n => {
        const div = document.createElement('div');
        div.className = 'carte-node';
        div.dataset.id = n.id;
        div.style.left = n.x + 'px';
        div.style.top = n.y + 'px';
        div.style.background = n.color || '#6366f1';
        div.style.cursor = window.carteEditable ? 'grab' : 'default';

        // On construit le texte via textContent (jamais via innerHTML) pour que
        // des caractères comme < > & tapés dans le nœud restent du texte brut
        // et ne soient jamais interprétés comme des balises HTML.
        const textEl = document.createElement('div');
        textEl.className = 'node-text';
        textEl.contentEditable = window.carteEditable ? 'true' : 'false';
        textEl.textContent = n.text;
        div.appendChild(textEl);

        if (window.carteEditable) {
            const tools = document.createElement('div');
            tools.className = 'node-tools';
            tools.innerHTML = `<span onclick="cycleColor('${n.id}')">🎨</span>
                <span onclick="startLink('${n.id}')">🔗</span>
                <span onclick="deleteNode('${n.id}')">🗑</span>`;
            div.appendChild(tools);

            textEl.addEventListener('blur', ev => { n.text = ev.target.innerText; });
            textEl.addEventListener('mousedown', ev => ev.stopPropagation());
            makeCarteNodeDraggable(div, n);
        }
        layer.appendChild(div);
    });
}

function makeCarteNodeDraggable(div, n) {
    let dragging = false, offX = 0, offY = 0;
    div.addEventListener('mousedown', e => {
        if (e.target.closest('.node-tools')) return;
        dragging = true;
        const rect = div.getBoundingClientRect();
        offX = e.clientX - rect.left; offY = e.clientY - rect.top;
        div.style.cursor = 'grabbing';
    });
    document.addEventListener('mousemove', e => {
        if (!dragging) return;
        const canvas = document.getElementById('carte-canvas');
        const rect = canvas.getBoundingClientRect();
        n.x = Math.max(0, e.clientX - rect.left + canvas.scrollLeft - offX);
        n.y = Math.max(0, e.clientY - rect.top + canvas.scrollTop - offY);
        renderCarte();
    });
    document.addEventListener('mouseup', () => { dragging = false; div.style.cursor = 'grab'; });
}

function addNode() {
    const idx = (window.carteNodes || []).length;
    const id = 'n' + Date.now() + '_' + idx;
    window.carteNodes.push({ id: id, x: 120 + (idx % 5) * 40, y: 100 + (idx % 5) * 30, text: 'Nouvelle idée', color: CARTE_COLORS[idx % CARTE_COLORS.length] });
    renderCarte();
}

function cycleColor(id) {
    const n = window.carteNodes.find(x => x.id === id);
    if (!n) return;
    const i = CARTE_COLORS.indexOf(n.color);
    n.color = CARTE_COLORS[(i + 1) % CARTE_COLORS.length];
    renderCarte();
}

function startLink(id) {
    if (!carteLinkFrom) {
        carteLinkFrom = id;
    } else {
        if (carteLinkFrom !== id) {
            window.carteEdges.push({ from: carteLinkFrom, to: id });
        }
        carteLinkFrom = null;
        renderCarte();
    }
}

function deleteNode(id) {
    window.carteNodes = window.carteNodes.filter(n => n.id !== id);
    window.carteEdges = window.carteEdges.filter(e => e.from !== id && e.to !== id);
    renderCarte();
}

function saveCarte() {
    document.querySelectorAll('.node-text').forEach(el => {
        const n = window.carteNodes.find(x => x.id === el.closest('.carte-node').dataset.id);
        if (n) n.text = el.innerText;
    });
    fetch('/admin/cartes/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            id: window.carteId || '',
            titre: document.getElementById('carte-titre').value || 'Sans titre',
            nodes: window.carteNodes,
            edges: window.carteEdges
        })
    }).then(r => r.json()).then(d => { if (d.ok) window.location.href = '/admin/cartes'; });
}

// --- MINI WORD : MOTEUR ---
function miniExec(id, cmd, val) {
    const el = document.getElementById(id);
    if (!el) return;
    el.focus();
    document.execCommand(cmd, false, val || null);
}

function miniInsertImage(id) {
    const input = document.getElementById(id + '-file');
    if (input) input.click();
}

function miniHandleImage(id, input) {
    const file = input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = e => {
        const el = document.getElementById(id);
        el.focus();
        document.execCommand('insertImage', false, e.target.result);
    };
    reader.readAsDataURL(file);
    input.value = '';
}

// --- DEVOIRS DE CODE : EXÉCUTION DES TESTS AUTOMATIQUES ---
function escapeHtml(s) {
    const d = document.createElement('div');
    d.innerText = (s === undefined || s === null) ? '' : String(s);
    return d.innerHTML;
}

async function runDevoirTests(did) {
    const out = document.getElementById('test-results-' + did);
    const editor = document.getElementById('code-editor-' + did);
    const tests = window['tests_' + did] || [];
    if (!out || !editor) return;

    if (!py) {
        out.innerHTML = '<p style="color:var(--warning);">🐍 Python est en cours de chargement, réessaie dans un instant...</p>';
        return;
    }
    if (tests.length === 0) {
        out.innerHTML = '<p style="color:var(--text-dim);">Aucun test défini pour cet exercice.</p>';
        return;
    }

    out.innerHTML = '<p style="color:var(--text-dim);">⏳ Exécution des tests...</p>';
    let passed = 0;
    const results = [];

    for (const t of tests) {
        try {
            await py.runPythonAsync("import sys, io\nsys.stdout = io.StringIO()");
            await py.runPythonAsync(editor.value + "\n" + t.harnais);
            const obtenu = (await py.runPythonAsync("sys.stdout.getvalue()")).trim();
            const ok = obtenu.toLowerCase() === (t.attendu || '').toLowerCase().trim();
            if (ok) passed++;
            results.push({ nom: t.nom, passed: ok, attendu: t.attendu, obtenu: obtenu });
        } catch (e) {
            results.push({ nom: t.nom, passed: false, attendu: t.attendu, obtenu: 'Erreur : ' + e });
        }
    }

    const score = Math.round((passed / tests.length) * 100);
    let html = `<div style="font-weight:800; margin-bottom:12px; font-size:1rem;">
        Score : ${passed}/${tests.length} tests réussis (${score}%)
    </div>`;
    results.forEach(r => {
        html += `<div style="padding:12px 16px; margin-bottom:8px; border-radius:10px; font-size:0.85rem;
            background:${r.passed ? 'rgba(16,185,129,0.08)' : 'rgba(244,63,94,0.08)'};
            border-left:4px solid ${r.passed ? 'var(--success)' : 'var(--danger)'};">
            <b>${r.passed ? '✅' : '❌'} ${escapeHtml(r.nom)}</b><br>
            <span style="color:var(--text-dim);">Attendu : <code>${escapeHtml(r.attendu)}</code> — Obtenu : <code>${escapeHtml(r.obtenu)}</code></span>
        </div>`;
    });
    out.innerHTML = html;

    const scoreField = document.getElementById('auto-score-' + did);
    const resultsField = document.getElementById('auto-results-' + did);
    if (scoreField) scoreField.value = score;
    if (resultsField) resultsField.value = JSON.stringify(results);
}
</script>
<div id="level-up-overlay">
    <p style="color: var(--primary); font-weight: 800; letter-spacing: 5px;">NOUVEAU RANG ATTEINT</p>
    <h1 class="lvl-text">LEVEL UP !</h1>
    <p id="new-lvl-nb" style="font-size: 2rem; font-weight: 800; color: #fff;"></p>
    <button class="btn btn-primary" style="margin-top: 30px;" onclick="this.parentElement.style.display='none'">CONTINUER</button>
</div>
<div id="toast">Modifications enregistrées !</div>
</body>
</html>
"""

# --- LOGIQUE SERVEUR ---

@app.route("/")
def index():
    if "user" in session:
        return redirect(url_for('dashboard'))
    return render_template_string(LAYOUT, page='login')

@app.route("/quiz/<id_c>/<int:index>")
def view_quiz(id_c, index):
    if "user" not in session:
        return redirect("/")

    if id_c not in COURS:
        return redirect("/dashboard")

    cours_data = COURS[id_c]
    exercices = cours_data.get("exercices", [])

    if index >= len(exercices):
        return redirect(f"/resultat/{id_c}/0")

    exo = exercices[index]

    return render_template_string(
        LAYOUT,
        page="quiz",
        exos=exo,
        index=index,
        total=len(exercices),
        cours_id=id_c
    )

@app.route("/login", methods=["POST"])
def login():
    u = request.form.get("username", "").strip()
    if u:
        session["user"] = u
        if u not in USERS:
            USERS[u] = {"score": 0, "notes": {}}
        save_db()
        return redirect(url_for('dashboard'))
    return redirect(url_for('index'))

# @app.before_request
# def restrict_admin():
#    if request.path.startswith("/admin") and session.get("user") != "LearnCodePRO":
#        return redirect("/")
    


@app.route("/logout")
def logout(): session.clear(); return redirect("/")

@app.route("/dashboard")
def dashboard():
    if "user" not in session: return redirect("/")
    u = session["user"]
    username = session["user"]["username"] if isinstance(session["user"], dict) else session["user"]
    ud = USERS.get(username)
    
    # Si ud est None, on crée un profil par défaut pour éviter le crash
    if not ud:
        ud = {"xp": 0, "cours_termines": [], "devoirs_faits": []}
    # Calcul des notifs
    notifs = 0
    if u != "LearnCodePRO":
        notifs = sum(1 for d in DEVOIRS.values() if u in d["rendus"] and d["rendus"][u].get("note") and not d["rendus"][u].get("vu"))
    
   
    if "user" not in session: return redirect("/")
    
    lvl_data = get_level_data(ud.get("score", 0))
    
    cats = {}
    for cid, info in COURS.items():
        m = info.get("matiere", "GÉNÉRAL").upper()
        cats.setdefault(m, []).append((cid, info))
    
    if "user" not in session: return redirect("/")
    u = session["user"]
    # Calcul des notifs
    notifs = 0
    if u != "LearnCodePRO":
        notifs = sum(1 for d in DEVOIRS.values() if u in d["rendus"] and d["rendus"][u].get("note") and not d["rendus"][u].get("vu"))
    
    # ... reste du code ...
    return render_template_string(LAYOUT, page='dashboard', user_data=ud, 
                                 categories=cats, lvl=lvl_data, notifs=notifs)
@app.route("/admin/devoirs/creer", methods=["POST"])
def admin_creer_devoir():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    titre = request.form.get("titre")
    consigne_form = request.form.get("consigne", "Pas de consigne spécifiée.")
    did = "dev_" + str(hash(titre + str(datetime.now())))[:8] # ID unique
    DEVOIRS[did] = {"titre": titre, "rendus": {}}
    save_db()
    return redirect(url_for('admin_casier'))

@app.route("/update_score", methods=['POST'])
def update_score():
    d = request.json
    u = session.get("user")
    cid = d['id']
    score_final = int(d['score'])
    
    if u and cid in COURS:
        ud = USERS[u]
        old_note = ud["notes"].get(cid, 0)
        
        if score_final > old_note:
            # --- LA MODIFICATION EST ICI ---
            # On calcule la progression réelle, mais on ne donne qu'une fraction en XP
            diff_score = score_final - old_note
            gain_xp = diff_score // 4  # Divise par 4 (100% -> 25 XP)
            
            ud["score"] += gain_xp
            ud["notes"][cid] = score_final
            save_db()
            
            new_lvl_data = get_level_data(ud["score"])
            old_lvl_data = get_level_data(ud["score"] - gain_xp)
            
            return jsonify(
                ok=True, 
                level_up=(new_lvl_data["lvl"] > old_lvl_data["lvl"]), 
                new_level=new_lvl_data["lvl"]
            )
    return jsonify(ok=True, level_up=False)

@app.route("/cours/<id_c>")
def view_cours(id_c):
      if id_c not in COURS: return redirect("/")
      return render_template_string(LAYOUT, page='cours', cours=COURS[id_c], cours_id=id_c)



@app.route("/stats")
def stats_view():
    if "user" not in session: return redirect("/")
    u = session["user"]
    ud = USERS.get(u, {"score": 0, "notes": {}})
    
    # 1. Calcul des statistiques de base
    notes_list = list(ud["notes"].values())
    moy = int(sum(notes_list)/len(notes_list)) if notes_list else 0
    total_xp = ud.get("score", 0)
    nb_cours = len(ud["notes"])
    moy = int(sum(notes_list)/len(notes_list)) if notes_list else 0
    moy = min(moy, 100) # Sécurité ultime
    
    all_scores = []
    for name, data in USERS.items():
        all_scores.append({"name": name, "score": data.get("score", 0)})
    
    # Tri par score décroissant
    all_scores = sorted(all_scores, key=lambda x: x["score"], reverse=True)
    
    # Trouver la position de l'utilisateur actuel
    # On ajoute +1 car l'index commence à 0
    rank = next((i for i, item in enumerate(all_scores) if item["name"] == u), None)
    
    # 2. Système de Badges
    badges = []
    if nb_cours >= 1:
        badges.append({"n": "Premier Pas", "i": "🌱", "d": "A complété son premier module", "c": "#10b981"})
    if any(s == 100 for s in notes_list):
        badges.append({"n": "Perfectionniste", "i": "🎯", "d": "A obtenu 100% sur un module", "c": "#fbbf24"})
    if total_xp >= 500:
        badges.append({"n": "Vétéran", "i": "🛡️", "d": "A accumulé plus de 500 XP", "c": "#6366f1"})
    if nb_cours >= 5:
        badges.append({"n": "Série de 5", "i": "🔥", "d": "A validé 5 modules différents", "c": "#f43f5e"})
    if moy >= 90 and nb_cours >= 3:
        badges.append({"n": "Major de Promo", "i": "🎓", "d": "Moyenne supérieure à 90%", "c": "#a855f7"})
    if "bases" in ud["notes"] and "condition" in ud["notes"]: # Exemple de dépendance
        badges.append({"n": "Codeur Logic", "i": "🧠", "d": "Maîtrise les bases et les fonctions", "c": "#22d3ee"})
    if total_xp >= 1000:
        badges.append({"n": "Légende du Code", "i": "👑", "d": "Expert ultime (1000+ XP)", "c": "#ffffff"})
    if nb_cours >= 10:
        badges.append({"n": "Boulimique du Code", "i": "📚", "d": "A validé 10 modules", "c": "#3b82f6"})
    if rank is not None and nb_cours >= 3: # Condition de 3 cours pour éviter les faux espoirs au début
        if rank == 0:
            badges.append({"n": "Numéro 1", "i": "🥇", "d": "Le roi de la plateforme ! (1er)", "c": "#facc15"})
        elif rank == 1:
            badges.append({"n": "Dauphin", "i": "🥈", "d": "Sur la deuxième marche du podium", "c": "#94a3b8"})
        elif rank == 2:
            badges.append({"n": "Médaillé de Bronze", "i": "🥉", "d": "Dans le top 3 mondial !", "c": "#b45309"})
    
    # Badge Spécialiste (Focus sur une matière)
    # On compte combien de modules d'une même catégorie ont été validés
    cat_counts = {}
    for cid in ud["notes"]:
        cat = COURS[cid].get("matiere", "").upper()
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    if any(count >= 4 for count in cat_counts.values()):
        badges.append({"n": "Spécialiste", "i": "🧬", "d": "A validé 4 modules dans une même catégorie", "c": "#ec4899"})

    # Badge Top Score (Moyenne d'excellence)
    if moy >= 95 and nb_cours >= 5:
        badges.append({"n": "Élite du Dashboard", "i": "✨", "d": "Moyenne exceptionnelle de 95%+", "c": "#f59e0b"})

    # Badge Explorateur (Diversité)
    if len(cat_counts) >= 3:
        badges.append({"n": "Polyvalent", "i": "🌍", "d": "A exploré au moins 3 matières différentes", "c": "#14b8a6"})

    # Badge Challenge (Devoirs)
    nb_devoirs = len([d for d in DEVOIRS.values() if u in d["rendus"] and d["rendus"][u].get("note") is not None])
    if nb_devoirs >= 1:
        badges.append({"n": "Apprenti Appliqué", "i": "📝", "d": "A reçu sa première note sur un devoir", "c": "#8b5cf6"})
    if nb_devoirs >= 5:
        badges.append({"n": "Scribe du Code", "i": "📜", "d": "A complété 5 devoirs écrits", "c": "#4ade80"})
    # Note : Nécessite que tu comptes les devoirs dans ton dictionnaire utilisateur
    
    # 1. Calcul du classement (à insérer avant la liste des badges)
    
    # Leaderboard (inchangé)
    lb = []
    for n, d in USERS.items():
        nl = d.get("notes", {}).values()
        m = int(sum(nl)/len(nl)) if nl else 0
        lb.append({"name": n, "score": d.get("score", 0), "moy": m, "courses": len(d.get("notes", {}))})
    lb = sorted(lb, key=lambda x: x["score"], reverse=True)[:10]

    grade = "S+" if moy >= 95 else "S" if moy >= 85 else "A" if moy >= 70 else "B" if moy >= 50 else "C"
    
    return render_template_string(LAYOUT, page='stats', score=total_xp, moyenne=moy, 
                                 grade=grade, leaderboard=lb, chart_labels=list(ud["notes"].keys()), 
                                 chart_data=notes_list, badges=badges)



@app.route("/projet")
def view_projet(): return render_template_string(LAYOUT, page='projet')

@app.route("/admin")
def admin_dashboard():
    # Vérifie si c'est bien l'admin qui est connecté
    if session.get("user") != "LearnCodePRO": 
        return redirect("/")
    
    # On affiche la page admin avec la liste des cours et des devoirs
    return render_template_string(LAYOUT, page='admin_list', cours_dict=COURS, DEVOIRS=DEVOIRS, USERS=USERS)

@app.route("/admin/new")
def admin_new():
      if session.get("user") != "LearnCodePRO": return redirect("/")
      return render_template_string(LAYOUT, page='admin_edit', edit_mode=False, cours_to_edit={"exercices":[]})
@app.route("/admin/edit/<id_c>")
def admin_edit(id_c):
    # 1. Vérification de sécurité (Admin uniquement)
    if session.get("user") != "LearnCodePRO": 
        return redirect("/")
    
    # 2. On cherche le cours dans notre dictionnaire COURS
    # Si id_c n'existe pas (cas d'un nouveau cours), on crée une structure vide
    cours = COURS.get(id_c, {
        "titre": "", 
        "matiere": "", 
        "contenu": "", 
        "exercices": [], 
        "slides": []
    })
    
    # 3. On affiche la page 'admin_edit' du LAYOUT
    return render_template_string(
        LAYOUT, 
        page='admin_edit', 
        edit_mode=True, 
        edit_id=id_c, 
        cours_to_edit=cours,
        cours_dict=COURS # Nécessaire pour afficher la liste sur le côté si besoin
    )
@app.route("/admin/save", methods=["POST"])
def admin_save():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    
    cid = request.form.get("id")
    if not cid: return redirect("/admin")

    # --- 1. RÉCUPÉRATION DES SLIDES ---
    s_titres = request.form.getlist("slide_titre[]")
    s_contenus = request.form.getlist("slide_contenu[]")
    s_codes = request.form.getlist("slide_code[]")
    
    slides_finales = []
    for i in range(len(s_titres)):
        if s_titres[i].strip() or s_contenus[i].strip():
            slides_finales.append({
                "titre": s_titres[i],
                "contenu": s_contenus[i],
                "code": s_codes[i]
            })

    # --- 2. RÉCUPÉRATION DES EXERCICES ---
    qs = request.form.getlist("q[]")
    ts = request.form.getlist("type[]")
    os = request.form.getlist("opts[]")
    rs = request.form.getlist("r[]")
    # Pour les checkboxes, on récupère les index cochés
    pys = request.form.getlist("is_py[]") 

    exos_final = []
    for i in range(len(qs)):
        exos_final.append({
            "q": qs[i],
            "type": ts[i],
            "opts": os[i].split(",") if os[i] else [],
            "r": rs[i],
            "is_python": str(i) in pys  # Vérifie si l'index i est dans la liste des cochés
        })

    # --- 3. MISE À JOUR GLOBALE ---
    COURS[cid] = {
        "titre": request.form.get("titre"),
        "matiere": request.form.get("matiere"),
        "contenu": request.form.get("contenu"),
        "slides": slides_finales,
        "exercices": exos_final
    }

    save_db()
    return redirect("/admin")



# --- CARTES MENTALES ---

@app.route("/cartes")
def liste_cartes():
    if "user" not in session: return redirect("/")
    return render_template_string(LAYOUT, page='cartes_eleve', cartes=CARTES)

@app.route("/cartes/voir/<cid>")
def voir_carte(cid):
    if "user" not in session: return redirect("/")
    carte = CARTES.get(cid)
    if not carte: return redirect("/cartes")
    return render_template_string(LAYOUT, page='carte_view', carte=carte, carte_id=cid)

@app.route("/admin/cartes")
def admin_cartes_list():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    return render_template_string(LAYOUT, page='admin_cartes_list', cartes=CARTES)

@app.route("/admin/cartes/new")
def admin_cartes_new():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    return render_template_string(LAYOUT, page='carte_editor', carte={"titre": "", "nodes": [], "edges": []}, carte_id="")

@app.route("/admin/cartes/edit/<cid>")
def admin_cartes_edit(cid):
    if session.get("user") != "LearnCodePRO": return redirect("/")
    carte = CARTES.get(cid, {"titre": "", "nodes": [], "edges": []})
    return render_template_string(LAYOUT, page='carte_editor', carte=carte, carte_id=cid)

@app.route("/admin/cartes/save", methods=["POST"])
def admin_cartes_save():
    if session.get("user") != "LearnCodePRO": return jsonify(ok=False), 403
    data = request.get_json(force=True, silent=True) or {}
    cid = data.get("id") or f"carte_{int(datetime.now().timestamp())}"
    CARTES[cid] = {
        "titre": data.get("titre", "Sans titre"),
        "nodes": data.get("nodes", []),
        "edges": data.get("edges", []),
        "date": datetime.now().strftime("%d/%m/%Y"),
    }
    save_db()
    return jsonify(ok=True, id=cid)

@app.route("/admin/cartes/delete/<cid>")
def admin_cartes_delete(cid):
    if session.get("user") != "LearnCodePRO": return redirect("/")
    CARTES.pop(cid, None)
    save_db()
    return redirect("/admin/cartes")

# --- DOCUMENTS (MINI WORD) ---

@app.route("/documents/voir/<did>")
def voir_document(did):
    if "user" not in session: return redirect("/")
    doc = DOCUMENTS.get(did)
    if not doc: return redirect("/dashboard")
    return render_template_string(LAYOUT, page='doc_view', doc=doc)

@app.route("/admin/documents")
def admin_documents_list():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    return render_template_string(LAYOUT, page='admin_documents_list', documents=DOCUMENTS)

@app.route("/admin/documents/new")
def admin_documents_new():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    return render_template_string(LAYOUT, page='doc_editor', doc={"titre": "", "contenu": ""}, doc_id="")

@app.route("/admin/documents/edit/<did>")
def admin_documents_edit(did):
    if session.get("user") != "LearnCodePRO": return redirect("/")
    doc = DOCUMENTS.get(did, {"titre": "", "contenu": ""})
    return render_template_string(LAYOUT, page='doc_editor', doc=doc, doc_id=did)

@app.route("/admin/documents/save", methods=["POST"])
def admin_documents_save():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    did = request.form.get("id") or f"doc_{int(datetime.now().timestamp())}"
    DOCUMENTS[did] = {
        "titre": request.form.get("titre", "Sans titre"),
        "contenu": request.form.get("contenu", ""),
        "date": datetime.now().strftime("%d/%m/%Y"),
    }
    save_db()
    return redirect("/admin/documents")

@app.route("/admin/documents/delete/<did>")
def admin_documents_delete(did):
    if session.get("user") != "LearnCodePRO": return redirect("/")
    DOCUMENTS.pop(did, None)
    save_db()
    return redirect("/admin/documents")


@app.route("/casier")
def admin_casier():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    return render_template_string(LAYOUT, page='admin_casier', devoirs=DEVOIRS, USERS=USERS, documents=DOCUMENTS, cartes=CARTES)

@app.route("/casier/nouveau", methods=["POST"])
def nouveau_devoir():
    if session.get("user") != "LearnCodePRO": 
        return redirect("/")
    
    # 1. On crée l'ID unique
    did = f"dev_{int(datetime.now().timestamp())}"
    
    # 2. ON RÉCUPÈRE LE TITRE DEPUIS LE FORMULAIRE (C'est ce qui manquait !)
    titre_form = request.form.get("titre", "Sans titre") 
    consigne_form = request.form.get("consigne", "Faites l'exercice.")
    attachments = request.form.getlist("attach[]")
    type_devoir = request.form.get("type_devoir", "texte")

    # 3. On enregistre dans le dictionnaire
    DEVOIRS[did] = {
        "titre": titre_form,
        "consigne": consigne_form,
        "rendus": {},
        "date": datetime.now().strftime("%d/%m/%Y"),
        "documents": attachments,
        "type": type_devoir,
    }

    # 4. Si c'est un devoir de code, on enregistre le code de départ et les tests automatiques
    if type_devoir == "code":
        noms = request.form.getlist("test_nom[]")
        harnais = request.form.getlist("test_harnais[]")
        attendus = request.form.getlist("test_attendu[]")
        tests = []
        for i in range(len(noms)):
            if noms[i].strip() or harnais[i].strip():
                tests.append({
                    "nom": noms[i].strip() or f"Test {i + 1}",
                    "harnais": harnais[i],
                    "attendu": attendus[i] if i < len(attendus) else "",
                })
        DEVOIRS[did]["code_depart"] = request.form.get("code_depart", "")
        DEVOIRS[did]["tests"] = tests
    
    save_db()
    return redirect("/casier")

@app.route("/casier/corriger/<did>/<student>", methods=["POST"])
def corriger_devoir(did, student):
    if session.get("user") != "LearnCodePRO": return redirect("/")
    note = request.form.get("note")
    feedback = request.form.get("feedback")
    DEVOIRS[did]["rendus"][student].update({
        "note": note,
        "feedback": feedback,
        "vu": False # Déclenche la notification chez l'élève
    })
    save_db()
    return redirect("/casier")

@app.route("/devoirs")
def liste_devoirs():
    u = session.get("user")
    if not u: return redirect("/")
    
    # Assure-toi d'avoir USERS=USERS ici aussi
    return render_template_string(LAYOUT, 
                                  page='devoirs_eleve', 
                                  devoirs=DEVOIRS, 
                                  user=u, 
                                  USERS=USERS,
                                  documents=DOCUMENTS,
                                  cartes=CARTES)

@app.route("/devoirs/rendre/<did>", methods=["POST"])
def rendre_devoir(did):
    u = session.get("user")
    if not u or did not in DEVOIRS: 
        return redirect("/")
    reponse_doc = request.form.get("reponse_doc", "").strip()
    rendu = {
        "reponse": request.form.get("reponse", ""),
        "reponse_doc": reponse_doc if reponse_doc else None,
        "date": datetime.now().strftime("%d/%m %H:%M"),
        "note": None,
    }

    # Résultats des tests automatiques (devoirs de code), envoyés par le navigateur de l'élève
    auto_score_raw = request.form.get("auto_score", "").strip()
    auto_results_raw = request.form.get("auto_results", "").strip()
    if auto_score_raw:
        try: rendu["auto_score"] = float(auto_score_raw)
        except ValueError: pass
    if auto_results_raw:
        try: rendu["auto_results"] = json.loads(auto_results_raw)
        except (ValueError, TypeError): pass

    DEVOIRS[did]["rendus"][u] = rendu
    
    save_db()
    return redirect("/devoirs")

@app.route("/devoirs/consulter/<id_d>")
def consulter_corrige(id_d):
    if "user" not in session: return redirect("/")
    u = session["user"]
    
    devoir = DEVOIRS.get(id_d)
    if not devoir:
        return redirect("/devoirs")

    # --- AJOUTEZ CETTE LOGIQUE ICI ---
    rendu = devoir["rendus"].get(u)
    # Si le devoir a une note (il est corrigé) et qu'il n'est pas encore marqué comme vu
    if rendu and rendu.get("note") is not None and rendu.get("vu") == False:
        rendu["vu"] = True # On marque comme lu
        save_db() # On sauvegarde le changement dans le fichier JSON
    # ---------------------------------

    # On récupère les notifs mises à jour pour la barre de navigation
    notifs = compter_notifs(u) 
    return render_template_string(LAYOUT, page='voir_devoir', user=u, devoir=devoir, id_d=id_d, USERS=USERS, notifs=notifs, CARTES=CARTES, DOCUMENTS=DOCUMENTS)

@app.route("/admin/delete/<cid>")
def admin_delete(cid):
      if session.get("user") == "LearnCodePRO": COURS.pop(cid, None); save_db()
      return redirect("/admin")
# ROUTE 1 : Créer le devoir vide


# ROUTE 2 : Noter et Corriger
@app.route("/admin/casier/noter", methods=["POST"])
def admin_noter():
    if session.get("user") != "LearnCodePRO": return redirect("/")
    
    did = request.form.get("did")
    user_eleve = request.form.get("eleve")
    note_val = request.form.get("note")
    
    if did in DEVOIRS and user_eleve in DEVOIRS[did]["rendus"]:
        ud = USERS[user_eleve]
        rendu = DEVOIRS[did]["rendus"][user_eleve]
        
        if rendu.get("note") is None:
            try:
                gain_xp = int(float(note_val) * 5)
                
                # --- CALCUL DU LEVEL UP ---
                old_lvl = (ud["score"] // 100) + 1 # Ou ton palier actuel
                ud["score"] += gain_xp
                new_lvl = (ud["score"] // 100) + 1
                
                # Si le niveau a augmenté, on stocke l'info
                if new_lvl > old_lvl:
                    ud["pending_level_up"] = True 
                
            except: pass

        rendu.update({"note": note_val, "feedback": request.form.get("feedback"), "correction": request.form.get("correction"), "vu": False})
        save_db()
    return redirect(url_for('admin_casier'))
        # --------------------------------
@app.route("/clear_level_up")
def clear_level_up():
    u = session.get("user")
    if u in USERS:
        USERS[u]["pending_level_up"] = False
        save_db()
    return jsonify(ok=True)
@app.route("/resultat/<id_c>/<int:score>")
def view_resultat(id_c, score):
    if "user" not in session: return redirect("/")
    if id_c not in COURS: return redirect("/")
    
    cours = COURS[id_c]
    # Message personnalisé selon la note
    if score == 100: msg = "Parfait ! Vous maîtrisez ce sujet sur le bout des doigts. 🏆"
    elif score >= 80: msg = "Excellent travail ! Vous avez une très bonne compréhension. 🌟"
    elif score >= 50: msg = "Pas mal ! Encore un peu d'entraînement et ce sera parfait. 👍"
    else: msg = "C'est un bon début. N'hésitez pas à relire le cours pour progresser ! 💪"
    
    return render_template_string(LAYOUT, page='resultat', cours=cours, score=score, message=msg, cours_id=id_c, USERS=USERS)


if __name__ == "__main__":
      app.run(debug=True, port=5003)
