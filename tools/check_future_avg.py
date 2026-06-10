import sqlite3

conn = sqlite3.connect('data/fcbillar.db')
cur = conn.cursor()

# Get player 843
player_id = 2

# Totes les partides del jugador 843 (modalitat 1) ordenades per data desc
print("=== Totes les partides del jugador 843 (modalitat 1, últimes 20) ===")
cur.execute("""
SELECT g.id, g.data_partida, 
       CASE WHEN g.player1_id = ? THEN g.caramboles1 ELSE g.caramboles2 END AS caramboles,
       g.entrades,
       CASE WHEN g.entrades > 0 THEN 
         (CASE WHEN g.player1_id = ? THEN g.caramboles1 ELSE g.caramboles2 END) * 1.0 / g.entrades
       ELSE 0 END AS mitjana_partida
FROM games g
WHERE (g.player1_id = ? OR g.player2_id = ?) AND g.modalitat_id = 1
ORDER BY g.data_partida DESC
LIMIT 20
""", (player_id, player_id, player_id, player_id))

games_info = []
for row in cur.fetchall():
    print(row)
    games_info.append(row)

# Calcular la mitjana amb les últimes 15 partides
print("\n=== Mitjana amb últimes 15 partides ===")
last_15_games = games_info[:15]
total_caramboles = sum(g[2] for g in last_15_games if g[2])
total_entrades = sum(g[3] for g in last_15_games if g[3])
mitjana_15 = (total_caramboles / total_entrades) if total_entrades > 0 else 0

print(f"Total caramboles: {total_caramboles}")
print(f"Total entrades: {total_entrades}")
print(f"Mitjana últimes 15: {mitjana_15:.5f}")

# Calcular la mitjana amb totes les partides
print("\n=== Mitjana amb totes les partides ===")
cur.execute("""
SELECT COUNT(*),
       SUM(CASE WHEN g.player1_id = ? THEN g.caramboles1 ELSE g.caramboles2 END) AS total_caramboles,
       SUM(g.entrades) AS total_entrades
FROM games g
WHERE (g.player1_id = ? OR g.player2_id = ?) AND g.modalitat_id = 1
""", (player_id, player_id, player_id))

row = cur.fetchone()
if row:
    count, total_car, total_ent = row
    mitjana_total = (total_car / total_ent) if total_ent and total_ent > 0 else 0
    print(f"Total partides: {count}")
    print(f"Total caramboles: {total_car}")
    print(f"Total entrades: {total_ent}")
    print(f"Mitjana total: {mitjana_total:.5f}")

# Veure quin és el ranking entry més recent per a aquest jugador i modalitat
print("\n=== Ranking entry més recent (modalitat 1) ===")
cur.execute("""
SELECT r.num_seq, re.posicio, re.mitjana_general, re.partides, re.extras_json
FROM ranking_entries re
JOIN rankings r ON r.id = re.ranking_id
WHERE re.player_id = ? AND r.modalitat_id = 1
ORDER BY r.num_seq DESC
LIMIT 2
""", (player_id,))

import json
for row in cur.fetchall():
    num_seq, posicio, mitjana_general, partides, extras_json = row
    print(f"num_seq={num_seq}, posicio={posicio}, mitjana_general={mitjana_general}, partides={partides}")
    if extras_json:
        extras = json.loads(extras_json)
        print(f"  extras: {extras}")
    print()

conn.close()
