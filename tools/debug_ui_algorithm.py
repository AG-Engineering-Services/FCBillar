import sqlite3

conn = sqlite3.connect('data/fcbillar.db')
cur = conn.cursor()

# Get player 843
player_id = 2

# Get all games for modalitat 1, ordered by date desc
print("=== Totes les partides modalitat 1 (últimes 25) ordenades per data desc ===")
cur.execute("""
SELECT g.id, g.data_partida, 
       CASE WHEN g.player1_id = ? THEN g.caramboles1 ELSE g.caramboles2 END AS caramboles,
       g.entrades,
       CASE WHEN g.entrades > 0 THEN 
         (CASE WHEN g.player1_id = ? THEN g.caramboles1 ELSE g.caramboles2 END) * 1.0 / g.entrades
       ELSE 0 END AS mitjana
FROM games g
WHERE (g.player1_id = ? OR g.player2_id = ?) AND g.modalitat_id = 1
ORDER BY g.data_partida DESC
LIMIT 25
""", (player_id, player_id, player_id, player_id))

games_all = cur.fetchall()
for i, row in enumerate(games_all[:20], 1):
    print(f"{i:2}. {row[1]}: {row[2]}/{row[3]} = {row[4]:.4f}")

# Simulació de l'algoritme de la UI: ordena per data desc, després per mitjana desc
print("\n=== Após ordenar per data desc + mitjana desc dins dia ===")
# Agrupar per data i ordenar dins de cada dia per mitjana desc
from collections import defaultdict
by_date = defaultdict(list)
for row in games_all:
    by_date[row[1]].append(row)

# Ordenar dins de cada dia per mitjana desc
for date in by_date:
    by_date[date].sort(key=lambda x: x[4], reverse=True)

# Construcció ordenada (data desc, mitjana desc dentro)
sorted_games = []
for date in sorted(by_date.keys(), reverse=True):
    sorted_games.extend(by_date[date])

print("Primi 20:")
for i, row in enumerate(sorted_games[:20], 1):
    print(f"{i:2}. {row[1]}: {row[2]}/{row[3]} = {row[4]:.4f}")

# Calcular mitjana dels primers 15
print("\n=== Mitjana dels 15 primers (segons UI) ===")
first_15 = sorted_games[:15]
total_car = sum(g[2] for g in first_15)
total_ent = sum(g[3] for g in first_15)
mitjana_ui = total_car / total_ent if total_ent > 0 else 0
print(f"Total caramboles: {total_car}")
print(f"Total entrades: {total_ent}")
print(f"Mitjana UI (15 primers): {mitjana_ui:.5f}")

conn.close()
